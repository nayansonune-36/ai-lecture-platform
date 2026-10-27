import {
  useEffect,
  useRef,
  useState,
  useCallback,
  useImperativeHandle,
  forwardRef,
} from "react";
import Hls from "hls.js";
import { formatDuration } from "../utils/format.js";
import { useTranslation } from "../i18n/index.js";

export interface HlsPlayerRef {
  seekTo: (seconds: number) => void;
  play: () => void;
  pause: () => void;
  getCurrentTime: () => number;
}

interface HlsPlayerProps {
  manifestUrl: string;
  posterUrl?: string | null;
  captionsUrl?: string | null;
  initialPositionMs?: number;
  durationMs?: number;
  onProgressUpdate?: (positionMs: number, completed: boolean) => void;
  onTokenExpired?: () => void;
  onNetworkError?: () => void;
}

export const HlsPlayer = forwardRef<HlsPlayerRef, HlsPlayerProps>(function HlsPlayer(
  {
    manifestUrl,
    posterUrl,
    captionsUrl,
    initialPositionMs = 0,
    durationMs = 0,
    onProgressUpdate,
    onTokenExpired,
    onNetworkError,
  },
  ref
) {
  const { t } = useTranslation();
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const hlsRef = useRef<Hls | null>(null);

  // Player state
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(durationMs > 0 ? durationMs / 1000 : 0);
  const [volume, setVolume] = useState(1);
  const [isMuted, setIsMuted] = useState(false);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [captionsEnabled, setCaptionsEnabled] = useState(true);

  // Quality levels
  const [qualityLevels, setQualityLevels] = useState<{ id: number; height: number; bitrate: number }[]>([]);
  const [currentLevel, setCurrentLevel] = useState<number>(-1); // -1 = Auto

  // Menu toggles
  const [showSettingsMenu, setShowSettingsMenu] = useState(false);
  const [settingsTab, setSettingsTab] = useState<"main" | "quality" | "speed">("main");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [resumeToast, setResumeToast] = useState<string | null>(null);

  const hasResumedRef = useRef(false);

  // Resume playback position when initialPositionMs is provided
  useEffect(() => {
    if (!hasResumedRef.current && initialPositionMs > 0) {
      hasResumedRef.current = true;
      if (videoRef.current) {
        videoRef.current.currentTime = initialPositionMs / 1000;
      }
      setCurrentTime(initialPositionMs / 1000);
      setResumeToast(t("player.resume_from").replace("{time}", formatDuration(initialPositionMs)));
      const timer = setTimeout(() => setResumeToast(null), 4000);
      return () => clearTimeout(timer);
    }
  }, [initialPositionMs, t]);

  // Seek imperative handle
  useImperativeHandle(ref, () => ({
    seekTo: (seconds: number) => {
      if (videoRef.current) {
        videoRef.current.currentTime = Math.max(0, Math.min(seconds, duration || seconds));
      }
    },
    play: () => {
      videoRef.current?.play().catch(() => {});
    },
    pause: () => {
      videoRef.current?.pause();
    },
    getCurrentTime: () => videoRef.current?.currentTime ?? 0,
  }));

  // Save progress helper
  const reportProgress = useCallback(() => {
    if (!videoRef.current) return;
    const currentMs = Math.floor(videoRef.current.currentTime * 1000);
    if (currentMs === 0) return; // Do not overwrite saved progress with 0 on unmount/reload
    const totalMs = durationMs > 0 ? durationMs : Math.floor(videoRef.current.duration * 1000);
    const isCompleted = totalMs > 0 && totalMs - currentMs < 5000;
    onProgressUpdate?.(currentMs, isCompleted);
  }, [durationMs, onProgressUpdate]);

  // Periodic progress saving (every 10 seconds)
  useEffect(() => {
    const interval = setInterval(() => {
      if (videoRef.current && !videoRef.current.paused) {
        reportProgress();
      }
    }, 10000);

    return () => clearInterval(interval);
  }, [reportProgress]);

  // Save progress on page unload / component unmount
  useEffect(() => {
    const handleBeforeUnload = () => {
      reportProgress();
    };

    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
      reportProgress();
    };
  }, [reportProgress]);

  // Initialize HLS
  useEffect(() => {
    const video = videoRef.current;
    if (!video || !manifestUrl) return;

    setErrorMessage(null);

    if (Hls.isSupported()) {
      const queryIndex = manifestUrl.indexOf("?");
      const queryParams = queryIndex !== -1 ? manifestUrl.slice(queryIndex) : "";

      const hls = new Hls({
        enableWorker: true,
        lowLatencyMode: false,
        backBufferLength: 60,
        xhrSetup: (xhr, url) => {
          if (queryParams && !url.includes("?")) {
            xhr.open("GET", `${url}${queryParams}`, true);
          }
        },
      });

      hlsRef.current = hls;
      hls.attachMedia(video);

      hls.on(Hls.Events.MEDIA_ATTACHED, () => {
        hls.loadSource(manifestUrl);
      });

      hls.on(Hls.Events.MANIFEST_PARSED, (_event, data) => {
        const levels = data.levels.map((lvl, index) => ({
          id: index,
          height: lvl.height,
          bitrate: lvl.bitrate,
        }));
        setQualityLevels(levels);

        // Resume playback position once manifest is ready
        if (!hasResumedRef.current && initialPositionMs > 0) {
          hasResumedRef.current = true;
          const targetSeconds = initialPositionMs / 1000;
          video.currentTime = targetSeconds;
          setResumeToast(t("player.resume_from").replace("{time}", formatDuration(initialPositionMs)));
          setTimeout(() => setResumeToast(null), 4000);
        }
      });

      hls.on(Hls.Events.LEVEL_SWITCHED, (_event, data) => {
        setCurrentLevel(hls.autoLevelEnabled ? -1 : data.level);
      });

      hls.on(Hls.Events.ERROR, (_event, data) => {
        if (data.response && (data.response.code === 401 || data.response.code === 403)) {
          setErrorMessage(t("player.error_expired"));
          onTokenExpired?.();
          return;
        }

        if (data.fatal) {
          switch (data.type) {
            case Hls.ErrorTypes.NETWORK_ERROR:
              setErrorMessage(t("player.error_network"));
              onNetworkError?.();
              hls.startLoad();
              break;
            case Hls.ErrorTypes.MEDIA_ERROR:
              hls.recoverMediaError();
              break;
            default:
              hls.destroy();
              setErrorMessage(t("common.error"));
              break;
          }
        }
      });

      return () => {
        hls.destroy();
        hlsRef.current = null;
      };
    } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
      // Native iOS Safari HLS playback
      video.src = manifestUrl;
      video.addEventListener("loadedmetadata", () => {
        if (!hasResumedRef.current && initialPositionMs > 0) {
          hasResumedRef.current = true;
          video.currentTime = initialPositionMs / 1000;
        }
      });
    }
  }, [manifestUrl, initialPositionMs, onTokenExpired, onNetworkError, t]);

  // Video event handlers
  const handleTimeUpdate = () => {
    if (videoRef.current) {
      setCurrentTime(videoRef.current.currentTime);
      if (videoRef.current.duration && !isNaN(videoRef.current.duration)) {
        setDuration(videoRef.current.duration);
      }
    }
  };

  const handlePlayPause = () => {
    if (!videoRef.current) return;
    if (videoRef.current.paused) {
      videoRef.current.play().catch(() => {});
    } else {
      videoRef.current.pause();
      reportProgress();
    }
  };

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!videoRef.current) return;
    const newTime = parseFloat(e.target.value);
    videoRef.current.currentTime = newTime;
    setCurrentTime(newTime);
  };

  const handleVolumeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseFloat(e.target.value);
    setVolume(val);
    if (videoRef.current) {
      videoRef.current.volume = val;
      videoRef.current.muted = val === 0;
      setIsMuted(val === 0);
    }
  };

  const toggleMute = () => {
    if (!videoRef.current) return;
    const nextMuted = !isMuted;
    videoRef.current.muted = nextMuted;
    setIsMuted(nextMuted);
  };

  const handleSpeedChange = (speed: number) => {
    if (videoRef.current) {
      videoRef.current.playbackRate = speed;
      setPlaybackRate(speed);
      setShowSettingsMenu(false);
    }
  };

  const handleQualityChange = (levelIndex: number) => {
    if (hlsRef.current) {
      if (levelIndex === -1) {
        hlsRef.current.currentLevel = -1; // Auto
      } else {
        hlsRef.current.currentLevel = levelIndex;
      }
      setCurrentLevel(levelIndex);
      setShowSettingsMenu(false);
    }
  };

  const toggleFullscreen = () => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen().catch(() => {});
      setIsFullscreen(true);
    } else {
      document.exitFullscreen().catch(() => {});
      setIsFullscreen(false);
    }
  };

  const toggleCaptions = () => {
    if (!videoRef.current) return;
    const tracks = videoRef.current.textTracks;
    const nextState = !captionsEnabled;
    setCaptionsEnabled(nextState);
    for (let i = 0; i < tracks.length; i++) {
      tracks[i].mode = nextState ? "showing" : "disabled";
    }
  };

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't intercept if user is typing in an input
      if (["INPUT", "TEXTAREA", "SELECT"].includes((e.target as HTMLElement).tagName)) {
        return;
      }

      const video = videoRef.current;
      if (!video) return;

      switch (e.key.toLowerCase()) {
        case " ":
        case "k":
          e.preventDefault();
          handlePlayPause();
          break;
        case "arrowleft":
        case "j":
          e.preventDefault();
          video.currentTime = Math.max(0, video.currentTime - 10);
          break;
        case "arrowright":
        case "l":
          e.preventDefault();
          video.currentTime = Math.min(video.duration || 0, video.currentTime + 10);
          break;
        case "arrowup":
          e.preventDefault();
          video.volume = Math.min(1, video.volume + 0.1);
          setVolume(video.volume);
          setIsMuted(false);
          break;
        case "arrowdown":
          e.preventDefault();
          video.volume = Math.max(0, video.volume - 0.1);
          setVolume(video.volume);
          if (video.volume === 0) setIsMuted(true);
          break;
        case "m":
          e.preventDefault();
          toggleMute();
          break;
        case "f":
          e.preventDefault();
          toggleFullscreen();
          break;
        case "c":
          e.preventDefault();
          toggleCaptions();
          break;
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  });

  return (
    <div ref={containerRef} className={`custom-player-container ${isFullscreen ? "fullscreen" : ""}`}>
      {errorMessage && (
        <div className="player-error-overlay">
          <p>{errorMessage}</p>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => {
              setErrorMessage(null);
              hlsRef.current?.startLoad();
            }}
          >
            {t("common.retry")}
          </button>
        </div>
      )}

      {resumeToast && (
        <div className="player-toast" role="status">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
            <polygon points="5 3 19 12 5 21 5 3" />
          </svg>
          <span>{resumeToast}</span>
        </div>
      )}

      <video
        ref={videoRef}
        className="hls-video-element"
        poster={posterUrl || undefined}
        onTimeUpdate={handleTimeUpdate}
        onPlay={() => setIsPlaying(true)}
        onPause={() => {
          setIsPlaying(false);
          reportProgress();
        }}
        onClick={handlePlayPause}
        playsInline
      >
        {captionsUrl && (
          <track
            kind="captions"
            src={captionsUrl}
            srcLang="en"
            label="English"
            default={captionsEnabled}
          />
        )}
      </video>

      {/* Custom Video Controls Bar */}
      <div className="custom-controls-overlay">
        {/* Scrubber timeline */}
        <div className="timeline-wrapper">
          <input
            type="range"
            min={0}
            max={duration || 100}
            step={0.1}
            value={currentTime}
            onChange={handleSeek}
            className="timeline-slider"
            aria-label="Seek timeline"
          />
        </div>

        <div className="controls-row">
          <div className="controls-left">
            {/* Play/Pause */}
            <button
              type="button"
              className="ctrl-btn"
              onClick={handlePlayPause}
              aria-label={isPlaying ? t("player.pause") : t("player.play")}
            >
              {isPlaying ? (
                <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor">
                  <rect x="6" y="4" width="4" height="16" />
                  <rect x="14" y="4" width="4" height="16" />
                </svg>
              ) : (
                <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor">
                  <polygon points="5 3 19 12 5 21 5 3" />
                </svg>
              )}
            </button>

            {/* Volume & Mute */}
            <div className="volume-group">
              <button
                type="button"
                className="ctrl-btn"
                onClick={toggleMute}
                aria-label={isMuted ? "Unmute" : "Mute"}
              >
                {isMuted || volume === 0 ? (
                  <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
                    <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
                    <line x1="23" y1="9" x2="17" y2="15" stroke="currentColor" strokeWidth="2" />
                    <line x1="17" y1="9" x2="23" y2="15" stroke="currentColor" strokeWidth="2" />
                  </svg>
                ) : (
                  <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
                    <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
                    <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07" fill="none" stroke="currentColor" strokeWidth="2" />
                  </svg>
                )}
              </button>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={isMuted ? 0 : volume}
                onChange={handleVolumeChange}
                className="volume-slider"
                aria-label="Volume level"
              />
            </div>

            {/* Time display */}
            <span className="time-display">
              {formatDuration(currentTime * 1000)} / {formatDuration(duration * 1000)}
            </span>
          </div>

          <div className="controls-right">
            {/* Captions Toggle */}
            {captionsUrl && (
              <button
                type="button"
                className={`ctrl-btn ${captionsEnabled ? "active-ctrl" : ""}`}
                onClick={toggleCaptions}
                title={t("player.captions")}
                aria-label={t("player.captions")}
              >
                <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="2" y="4" width="20" height="16" rx="2" />
                  <path d="M7 15h4M15 15h2M7 11h2M13 11h4" />
                </svg>
              </button>
            )}

            {/* Settings & Quality Menu */}
            <div className="settings-wrapper">
              <button
                type="button"
                className="ctrl-btn"
                onClick={() => {
                  setShowSettingsMenu(!showSettingsMenu);
                  setSettingsTab("main");
                }}
                title="Settings"
                aria-label="Settings"
              >
                <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="3" />
                  <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
                </svg>
              </button>

              {showSettingsMenu && (
                <div className="player-menu-popup">
                  {settingsTab === "main" && (
                    <div className="menu-items">
                      <button
                        type="button"
                        className="menu-item"
                        onClick={() => setSettingsTab("speed")}
                      >
                        <span>{t("player.speed")}</span>
                        <span className="menu-item-val">{playbackRate}x ›</span>
                      </button>
                      <button
                        type="button"
                        className="menu-item"
                        onClick={() => setSettingsTab("quality")}
                      >
                        <span>{t("player.quality")}</span>
                        <span className="menu-item-val">
                          {currentLevel === -1
                            ? t("player.auto")
                            : `${qualityLevels[currentLevel]?.height || ""}p ›`}
                        </span>
                      </button>
                    </div>
                  )}

                  {settingsTab === "speed" && (
                    <div className="menu-items">
                      <button type="button" className="menu-item back-btn" onClick={() => setSettingsTab("main")}>
                        ‹ {t("player.speed")}
                      </button>
                      {[0.5, 0.75, 1, 1.25, 1.5, 2].map((s) => (
                        <button
                          key={s}
                          type="button"
                          className={`menu-item ${playbackRate === s ? "active-item" : ""}`}
                          onClick={() => handleSpeedChange(s)}
                        >
                          {s}x {playbackRate === s && "✓"}
                        </button>
                      ))}
                    </div>
                  )}

                  {settingsTab === "quality" && (
                    <div className="menu-items">
                      <button type="button" className="menu-item back-btn" onClick={() => setSettingsTab("main")}>
                        ‹ {t("player.quality")}
                      </button>
                      <button
                        type="button"
                        className={`menu-item ${currentLevel === -1 ? "active-item" : ""}`}
                        onClick={() => handleQualityChange(-1)}
                      >
                        {t("player.auto")} {currentLevel === -1 && "✓"}
                      </button>
                      {qualityLevels.map((lvl) => (
                        <button
                          key={lvl.id}
                          type="button"
                          className={`menu-item ${currentLevel === lvl.id ? "active-item" : ""}`}
                          onClick={() => handleQualityChange(lvl.id)}
                        >
                          {lvl.height}p {currentLevel === lvl.id && "✓"}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Fullscreen */}
            <button
              type="button"
              className="ctrl-btn"
              onClick={toggleFullscreen}
              aria-label="Toggle Fullscreen"
            >
              {isFullscreen ? (
                <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3" />
                </svg>
              ) : (
                <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3" />
                </svg>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
});
