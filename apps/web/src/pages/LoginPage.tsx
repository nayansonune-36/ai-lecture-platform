import { useState, useEffect, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.js";
import { useTranslation, type Language } from "../i18n/index.js";

type SubPage = "login" | "forgot-password" | "contact-administrator";

function PhoneIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M5.1 3.6 8 3l2 4.8-2.1 1.4a14 14 0 0 0 6.9 6.9l1.4-2.1 4.8 2-.6 2.9c-.2 1-1.1 1.7-2.1 1.6C10.4 19.7 4.3 13.6 3.5 5.7c-.1-1 .6-1.9 1.6-2.1Z" />
    </svg>
  );
}

function EyeIcon({ hidden }: { hidden: boolean }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M2.7 12s3.4-5.2 9.3-5.2 9.3 5.2 9.3 5.2-3.4 5.2-9.3 5.2S2.7 12 2.7 12Z" />
      <circle cx="12" cy="12" r="2.3" />
      {hidden && <path d="m4 4 16 16" />}
    </svg>
  );
}

function ArrowIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="m15 18-6-6 6-6" />
    </svg>
  );
}

const pageFromHash = (): SubPage => {
  const hash = window.location.hash.replace("#/", "").replace("#", "");
  if (hash === "forgot-password" || hash === "contact-administrator") {
    return hash;
  }
  return "login";
};

export function LoginPage() {
  const [subPage, setSubPage] = useState<SubPage>(pageFromHash);
  const rememberedName = localStorage.getItem("student-portal-username") ?? "";
  const [email, setEmail] = useState(rememberedName);
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(Boolean(rememberedName));
  const [showPassword, setShowPassword] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Forgot password & Contact Admin states
  const [resetId, setResetId] = useState("");
  const [resetSent, setResetSent] = useState(false);
  const [contactId, setContactId] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [contactMsg, setContactMsg] = useState("");
  const [contactSent, setContactSent] = useState(false);

  const { login, isAuthenticated, isLoading } = useAuth();
  const { t, language, setLanguage } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();

  const from = (location.state as { from?: { pathname: string } })?.from?.pathname || "/courses";

  useEffect(() => {
    const handleHashChange = () => setSubPage(pageFromHash());
    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  if (isLoading) {
    return (
      <div className="loading-screen" role="status">
        <div className="spinner" />
        <p>{t("common.loading")}</p>
      </div>
    );
  }

  if (isAuthenticated) {
    return <Navigate to={from} replace />;
  }

  const handleLoginSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!email || !password) return;

    setErrorMsg(null);
    setIsSubmitting(true);

    try {
      if (rememberMe) {
        localStorage.setItem("student-portal-username", email);
      } else {
        localStorage.removeItem("student-portal-username");
      }
      await login(email, password);
      navigate(from, { replace: true });
    } catch (err: unknown) {
      if (
        typeof err === "object" &&
        err !== null &&
        "status" in err &&
        (err as { status: number }).status === 429
      ) {
        setErrorMsg(t("auth.rate_limited"));
      } else {
        setErrorMsg(t("auth.invalid_creds"));
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleResetSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!resetId) return;
    setResetSent(true);
  };

  const handleContactSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!contactId || !contactEmail || !contactMsg) return;
    setContactSent(true);
  };

  const toggleLanguage = () => {
    const nextLang: Language = language === "en" ? "hi" : "en";
    setLanguage(nextLang);
  };

  return (
    <main className="portal-shell">
      <div className="content-panel">
        <div className="portal-top-bar">
          <div className="phone-line">
            <PhoneIcon />
            <span>{t("auth.college_phone")}</span>
          </div>
          <button
            type="button"
            className="lang-toggle-btn"
            onClick={toggleLanguage}
            title={language === "en" ? "हिंदी में बदलें" : "Switch to English"}
          >
            {language === "en" ? "हिन्दी" : "English"}
          </button>
        </div>

        <div className="intro">
          <p className="eyebrow">{t("auth.student_portal")}</p>
          <h1>
            {t("auth.gateway_title_1")}
            <br />
            {t("auth.gateway_title_2")}
          </h1>
          <p className="intro-copy">{t("auth.gateway_subtitle")}</p>
        </div>

        {subPage === "login" && (
          <section className="auth-card login-card" aria-labelledby="login-title">
            <div className="card-heading login-header">
              <div className="login-icon-badge" aria-hidden="true">
                <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                  <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
                </svg>
              </div>
              <h2 id="login-title">{t("auth.welcome")}</h2>
              <p className="login-subtitle">{t("auth.student_login_desc")}</p>
            </div>

            {errorMsg && (
              <div className="error-banner" role="alert">
                {errorMsg}
              </div>
            )}

            <form onSubmit={handleLoginSubmit} className="login-form">
              <label htmlFor="email">{t("auth.student_id_label")}</label>
              <input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                placeholder={t("auth.student_id_placeholder")}
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={isSubmitting}
              />

              <label htmlFor="password">{t("auth.password")}</label>
              <div className="password-field">
                <input
                  id="password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  placeholder="••••••••"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={isSubmitting}
                />
                <button
                  className="eye-button"
                  type="button"
                  aria-label={showPassword ? t("auth.hide_password") : t("auth.show_password")}
                  aria-pressed={showPassword}
                  onClick={() => setShowPassword((prev) => !prev)}
                  disabled={isSubmitting}
                >
                  <EyeIcon hidden={showPassword} />
                </button>
              </div>

              <div className="form-options">
                <label className="check-label">
                  <input
                    type="checkbox"
                    checked={rememberMe}
                    onChange={(e) => setRememberMe(e.target.checked)}
                    disabled={isSubmitting}
                  />
                  <span>{t("auth.remember_me")}</span>
                </label>
                <a
                  href="#forgot-password"
                  onClick={(e) => {
                    e.preventDefault();
                    window.location.hash = "forgot-password";
                    setSubPage("forgot-password");
                  }}
                >
                  {t("auth.forgot_password")}
                </a>
              </div>

              <button
                className="primary-button submit-btn"
                type="submit"
                disabled={isSubmitting || !email || !password}
              >
                {isSubmitting ? t("auth.signing_in") : t("auth.submit")}
              </button>
            </form>

            <div className="account-help">
              <p>{t("auth.no_account")}</p>
              <a
                href="#contact-administrator"
                onClick={(e) => {
                  e.preventDefault();
                  window.location.hash = "contact-administrator";
                  setSubPage("contact-administrator");
                }}
              >
                {t("auth.contact_admin")}
              </a>
            </div>
          </section>
        )}

        {subPage === "forgot-password" && (
          <section className="auth-card secondary-card" aria-labelledby="forgot-title">
            <a
              className="back-link"
              href="#login"
              onClick={(e) => {
                e.preventDefault();
                window.location.hash = "login";
                setSubPage("login");
              }}
            >
              <ArrowIcon />
              {t("auth.back_to_login")}
            </a>
            <div className="card-heading">
              <h2 id="forgot-title">{t("auth.forgot_password")}</h2>
              <p>{t("auth.forgot_desc")}</p>
            </div>
            <form onSubmit={handleResetSubmit}>
              <label htmlFor="reset-id">{t("auth.student_id_label")}</label>
              <input
                id="reset-id"
                placeholder={t("auth.student_id_placeholder")}
                required
                value={resetId}
                onChange={(e) => setResetId(e.target.value)}
              />
              <button className="primary-button" type="submit">
                {t("auth.send_reset")}
              </button>
              {resetSent && (
                <p className="form-message" role="status">
                  {t("auth.reset_sent")}
                </p>
              )}
            </form>
            <p className="page-note">
              {t("auth.need_more_help")}{" "}
              <a
                href="#contact-administrator"
                onClick={(e) => {
                  e.preventDefault();
                  window.location.hash = "contact-administrator";
                  setSubPage("contact-administrator");
                }}
              >
                {t("auth.contact_admin")}
              </a>
            </p>
          </section>
        )}

        {subPage === "contact-administrator" && (
          <section className="auth-card secondary-card contact-card" aria-labelledby="contact-title">
            <a
              className="back-link"
              href="#login"
              onClick={(e) => {
                e.preventDefault();
                window.location.hash = "login";
                setSubPage("login");
              }}
            >
              <ArrowIcon />
              {t("auth.back_to_login")}
            </a>
            <div className="card-heading">
              <h2 id="contact-title">{t("auth.contact_admin_title")}</h2>
              <p>{t("auth.contact_admin_desc")}</p>
            </div>
            <form onSubmit={handleContactSubmit}>
              <label htmlFor="contact-id">{t("auth.student_id_label")}</label>
              <input
                id="contact-id"
                placeholder={t("auth.student_id_placeholder")}
                required
                value={contactId}
                onChange={(e) => setContactId(e.target.value)}
              />
              <label htmlFor="contact-email">{t("auth.email")}</label>
              <input
                id="contact-email"
                type="email"
                placeholder="student@campus.local"
                required
                value={contactEmail}
                onChange={(e) => setContactEmail(e.target.value)}
              />
              <label htmlFor="contact-msg">{t("auth.how_can_we_help")}</label>
              <textarea
                id="contact-msg"
                placeholder={t("auth.describe_issue")}
                required
                value={contactMsg}
                onChange={(e) => setContactMsg(e.target.value)}
              />
              <button className="primary-button" type="submit">
                {t("auth.send_request")}
              </button>
              {contactSent && (
                <p className="form-message" role="status">
                  {t("auth.request_sent")}
                </p>
              )}
            </form>
          </section>
        )}
      </div>
      <aside className="campus-visual" aria-label="Campus visual" />
    </main>
  );
}
