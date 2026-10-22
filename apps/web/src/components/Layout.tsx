import { Link, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.js";
import { useTranslation, type Language } from "../i18n/index.js";
import type { TranslationKey } from "../i18n/en.js";

export function Layout() {
  const { user, logout, isAuthenticated } = useAuth();
  const { language, setLanguage, t } = useTranslation();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  const toggleLanguage = () => {
    const nextLang: Language = language === "en" ? "hi" : "en";
    setLanguage(nextLang);
  };

  const roleKey = user ? (`role.${user.role}` as TranslationKey) : null;

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="header-container">
          <Link to="/courses" className="brand-logo" aria-label="AI Lecture Platform Home">
            <svg
              className="brand-icon"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <polygon points="12 2 2 7 12 12 22 7 12 2}" />
              <path d="M2 17l10 5 10-5" />
              <path d="M2 12l10 5 10-5" />
            </svg>
            <span className="brand-title">{t("app.title")}</span>
          </Link>

          <nav className="header-nav">
            {isAuthenticated && (
              <Link to="/courses" className="nav-link">
                {t("nav.courses")}
              </Link>
            )}

            <button
              type="button"
              className="lang-toggle-btn"
              onClick={toggleLanguage}
              aria-label={`Switch to ${language === "en" ? "Hindi" : "English"}`}
            >
              {language === "en" ? "हिंदी" : "English"}
            </button>

            {isAuthenticated && user ? (
              <div className="user-profile-widget">
                <span className="user-name">{user.name}</span>
                {roleKey && <span className="user-role-badge">{t(roleKey)}</span>}
                <button
                  type="button"
                  className="logout-btn"
                  onClick={handleLogout}
                  title={t("nav.logout")}
                >
                  {t("nav.logout")}
                </button>
              </div>
            ) : (
              <Link to="/login" className="login-link-btn">
                {t("nav.login")}
              </Link>
            )}
          </nav>
        </div>
      </header>

      <main className="main-content">
        <div className="content-container">
          <Outlet />
        </div>
      </main>

      <footer className="app-footer">
        <div className="footer-container">
          <p>© 2026 {t("app.title")} • Offline-ready campus network</p>
        </div>
      </footer>
    </div>
  );
}
