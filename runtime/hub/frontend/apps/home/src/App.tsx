import { useState, useEffect, useCallback } from "react";
import type { Resource, ResourceGroup, UserQuotaInfo, UserDetail } from "@auplc/shared";
import { getResources, getMyQuota, getMyUsage } from "@auplc/shared";

type Theme = "light" | "dark";
function getInitialTheme(): Theme {
  const stored = localStorage.getItem("auplc-theme") as Theme | null;
  if (stored === "light" || stored === "dark") return stored;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}
function applyTheme(t: Theme) {
  document.documentElement.setAttribute("data-bs-theme", t);
  localStorage.setItem("auplc-theme", t);
}
applyTheme(getInitialTheme());

interface HomeData {
  server_active: boolean;
  server_url: string;
}

declare global {
  interface Window {
    HOME_DATA?: HomeData;
    AVAILABLE_RESOURCES?: string[];
  }
}

const jhdata = window.jhdata ?? {
  base_url: "/hub/",
  xsrf_token: "",
  user: "student",
};

const baseUrl = jhdata.base_url ?? "/hub/";

const homeData: HomeData = window.HOME_DATA ?? {
  server_active: false,
  server_url: `${baseUrl.replace(/\/?$/, "/")}user/${jhdata.user ?? "student"}/`,
};

function formatResourceSpecs(r: Resource): string {
  const req = r.requirements;
  const parts: string[] = [];
  const cpu = parseFloat(req.cpu);
  if (cpu > 0) parts.push(`${req.cpu} CPU`);
  const memNum = parseFloat(req.memory);
  if (memNum > 0) parts.push(req.memory.replace("Gi", "GB"));
  if (req["amd.com/gpu"]) parts.push(`${req["amd.com/gpu"]} GPU`);
  if (req["amd.com/npu"]) parts.push(`${req["amd.com/npu"]} NPU`);
  return parts.join(", ");
}

function getAcceleratorType(r: Resource): "gpu" | "npu" | "cpu" {
  if (r.requirements["amd.com/gpu"]) return "gpu";
  if (r.requirements["amd.com/npu"]) return "npu";
  return "cpu";
}

function getGreeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}


function formatMins(m: number): string {
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  const r = m % 60;
  return r > 0 ? `${h}h ${r}m` : `${h}h`;
}

function App() {
  const [serverActive, setServerActive] = useState(homeData.server_active);
  const [stopping, setStopping] = useState(false);
  const [showStopConfirm, setShowStopConfirm] = useState(false);
  const [showUsage, setShowUsage] = useState(false);
  const [usageData, setUsageData] = useState<UserDetail | null>(null);
  const [usageLoading, setUsageLoading] = useState(false);
  const [announcement, setAnnouncement] = useState<string | null>(null);
  const [groups, setGroups] = useState<ResourceGroup[]>([]);
  const [resourcesLoading, setResourcesLoading] = useState(true);
  const [resourcesError, setResourcesError] = useState<string | null>(null);
  const [stopError, setStopError] = useState<string | null>(null);
  const [quota, setQuota] = useState<UserQuotaInfo | null>(null);

  const [theme, setTheme] = useState<Theme>(getInitialTheme);
  const toggleTheme = useCallback(() => {
    setTheme(t => {
      const next = t === "light" ? "dark" : "light";
      applyTheme(next);
      return next;
    });
  }, []);

  useEffect(() => {
    getMyQuota().then(setQuota).catch(() => {});
  }, []);

  // Poll server status every 15s to keep launch bar in sync
  useEffect(() => {
    const poll = () => {
      fetch(`${baseUrl}api/users/${jhdata.user ?? "student"}`, {
        headers: { Accept: "application/json" },
      })
        .then((r) => (r.ok ? r.json() : null))
        .then((data) => {
          if (data) setServerActive(Boolean(data.server));
        })
        .catch(() => {});
    };
    const id = setInterval(poll, 15_000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    fetch(`${baseUrl}static/announcement.txt`)
      .then((resp) => {
        if (!resp.ok) throw new Error("Not found");
        return resp.text();
      })
      .then((data) => {
        if (data?.trim()) setAnnouncement(data.trim());
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    getResources()
      .then((data) => {
        const allowedKeys = window.AVAILABLE_RESOURCES ?? [];
        const hasFilter = allowedKeys.length > 0;
        const allowedSet = new Set(allowedKeys);

        const filtered = hasFilter
          ? data.groups
              .map((g) => ({
                ...g,
                resources: g.resources.filter((r) => allowedSet.has(r.key)),
              }))
              .filter((g) => g.resources.length > 0)
          : data.groups.filter((g) => g.resources.length > 0);

        setGroups(filtered);
      })
      .catch((err) => {
        setResourcesError(
          err instanceof Error ? err.message : "Failed to load resources",
        );
      })
      .finally(() => setResourcesLoading(false));
  }, []);

  const handleStopClick = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      e.nativeEvent.stopImmediatePropagation();
      if (stopping) return;
      setShowStopConfirm(true);
    },
    [stopping],
  );

  const doStop = useCallback(async () => {
    setShowStopConfirm(false);
    setStopping(true);
    setStopError(null);
    try {
      const resp = await fetch(
        `${baseUrl}api/users/${jhdata.user}/server`,
        {
          method: "DELETE",
          headers: { "X-XSRFToken": jhdata.xsrf_token ?? "" },
        },
      );
      if (resp.ok || resp.status === 204 || resp.status === 202) {
        setServerActive(false);
      } else {
        setStopError(`Failed to stop server (HTTP ${resp.status})`);
      }
    } catch {
      setStopError("Network error — could not reach the server");
    } finally {
      setStopping(false);
    }
  }, []);

  const openUsage = useCallback(() => {
    setShowUsage(true);
    setUsageLoading(true);
    getMyUsage(30)
      .then(setUsageData)
      .catch(() => setUsageData(null))
      .finally(() => setUsageLoading(false));
  }, []);

  const totalResources = groups.reduce(
    (sum, g) => sum + g.resources.length,
    0,
  );

  return (
    <div className="home-page">
      {/* Hero */}
      <section className="home-hero">
        <div className="container" style={{ position: "relative" }}>
          <nav className="hero-nav">
            <a href={`${baseUrl}spawn`}>
              <i className="fa fa-rocket"></i> Launch Server
            </a>
            <button className="hero-nav-btn" onClick={openUsage} type="button">
              <i className="fa fa-bar-chart"></i> Usage
            </button>
            {Boolean((jhdata as Record<string, unknown>).admin) && (
              <a href={`${baseUrl}admin/users`}>
                <i className="fa fa-cog"></i> Admin
              </a>
            )}
            <button className="theme-toggle" onClick={toggleTheme} title={theme === "light" ? "Dark mode" : "Light mode"}>
              <i className={`fa ${theme === "light" ? "fa-moon-o" : "fa-sun-o"}`}></i>
            </button>
          </nav>
          <p className="hero-greeting">
            {getGreeting()}, {jhdata.user ?? "student"}
          </p>
          <h1>
            Welcome to <span className="accent">AUP Learning Cloud</span>
          </h1>
          <p className="hero-desc">
            Experience next-generation AI acceleration with AMD ROCm. Launch
            GPU-powered Jupyter notebooks for deep learning, computer vision,
            LLMs, and more.
          </p>
        </div>
      </section>

      {/* Launch Bar */}
      <div className="container">
        <div className="launch-bar">
          <div
            className={`lb-icon ${serverActive ? "running" : "stopped"}`}
          >
            <i className="fa fa-server"></i>
          </div>
          <div className="lb-info">
            <div className="lb-title">
              My Server
              {serverActive ? (
                <span className="status-badge running">
                  <span className="status-dot running"></span> Running
                </span>
              ) : (
                <span className="status-badge stopped">
                  <span className="status-dot stopped"></span> Stopped
                </span>
              )}
            </div>
            <div className="lb-desc">
              {stopError ? (
                <span className="lb-error">{stopError}</span>
              ) : stopping
                ? "Stopping your server\u2026"
                : serverActive
                  ? 'Your server is running \u2014 click "My Server" to open JupyterLab'
                  : "Choose a resource below and launch your Jupyter environment"}
              {quota?.enabled && (
                <span className="lb-quota-inline">
                  {" · Quota: "}
                  {quota.unlimited ? "Unlimited" : `${quota.balance}h remaining`}
                </span>
              )}
            </div>
          </div>
          <div className="lb-actions">
            {serverActive ? (
              <>
                <a
                  id="stop"
                  role="button"
                  className={`btn-home-sm danger${stopping ? " disabled" : ""}`}
                  onClick={handleStopClick}
                >
                  <i
                    className={`fa ${stopping ? "fa-spinner fa-spin" : "fa-stop"}`}
                  ></i>{" "}
                  {stopping ? "Stopping\u2026" : "Stop My Server"}
                </a>
                <a
                  id="start"
                  role="button"
                  className={`btn-launch${stopping ? " disabled" : ""}`}
                  href={stopping ? undefined : homeData.server_url}
                  onClick={stopping ? (e: React.MouseEvent) => e.preventDefault() : undefined}
                >
                  <i className={`fa ${stopping ? "fa-spinner fa-spin" : "fa-external-link"}`}></i>
                  {stopping ? " Stopping\u2026" : " My Server"}
                </a>
              </>
            ) : (
              <a
                id="start"
                role="button"
                className="btn-launch"
                href={`${baseUrl}spawn`}
              >
                <i className="fa fa-play"></i> Start My Server
              </a>
            )}
          </div>
        </div>
      </div>

      {/* Quick Start */}
      <div className="container">
        <section className="home-section" style={{ paddingBottom: "0.5rem" }}>
          <div className="qs-strip">
            <div className="qs-step">
              <div className="qs-num">1</div>
              <div className="qs-step-text">
                <h4>Choose a Resource</h4>
                <p>Pick a pre-configured environment below</p>
              </div>
            </div>
            <div className="qs-step">
              <div className="qs-num">2</div>
              <div className="qs-step-text">
                <h4>Configure &amp; Launch</h4>
                <p>Select GPU, set runtime, then launch</p>
              </div>
            </div>
            <div className="qs-step">
              <div className="qs-num">3</div>
              <div className="qs-step-text">
                <h4>Start Learning</h4>
                <p>Open notebooks and run experiments</p>
              </div>
            </div>
          </div>
        </section>
      </div>

      {/* Available Resources (dynamic from API) */}
      <div className="container">
        <section className="home-section">
          <div className="home-section-header">
            <h2>Available Resources</h2>
            {serverActive ? (
              <span style={{ fontSize: "0.78rem", color: "var(--home-text-muted)" }}>
                <i className="fa fa-info-circle"></i> Stop your server to launch a different resource
              </span>
            ) : (
              <a href={`${baseUrl}spawn`}>
                View all options{" "}
                <i
                  className="fa fa-arrow-right"
                  style={{ fontSize: "0.7rem" }}
                ></i>
              </a>
            )}
          </div>

          {resourcesLoading ? (
            <div className="resources-loading">
              <i className="fa fa-spinner fa-spin"></i> Loading resources…
            </div>
          ) : resourcesError ? (
            <div className="resources-error">
              <p>
                <strong>Error:</strong> {resourcesError}
              </p>
              <p>
                <a href={`${baseUrl}spawn`}>Go to Spawner</a>
              </p>
            </div>
          ) : totalResources === 0 ? (
            <div className="resources-empty">
              <p>
                No resources available.{" "}
                <a href={`${baseUrl}spawn`}>Go to Spawner</a>
              </p>
            </div>
          ) : (
            groups.map((group) => (
              <div className="resource-group" key={group.name}>
                <div className="resource-group-header">
                  <h3>{group.displayName}</h3>
                  <span className="group-count">
                    {group.resources.length}{" "}
                    {group.resources.length === 1 ? "resource" : "resources"}
                  </span>
                </div>
                <div className="resources-grid">
                  {group.resources.map((resource) => {
                    const accelType = getAcceleratorType(resource);
                    return (
                      <a
                        className={`resource-card${serverActive ? " disabled" : ""}`}
                        href={serverActive ? undefined : `${baseUrl}spawn?resource=${encodeURIComponent(resource.key)}`}
                        key={resource.key}
                        onClick={(e) => {
                          if (serverActive) { e.preventDefault(); }
                        }}
                        title={serverActive ? "Stop your running server first" : undefined}
                      >
                        <div className="resource-card-top">
                          <div className="resource-card-info">
                            <h4>
                              {resource.metadata?.description ?? resource.key}
                            </h4>
                            {resource.metadata?.subDescription && (
                              <p>{resource.metadata.subDescription}</p>
                            )}
                          </div>
                          <span className="resource-card-arrow">
                            <i className="fa fa-arrow-right"></i>
                          </span>
                        </div>
                        <div className="resource-card-tags">
                          <span
                            className={`resource-tag tag-${accelType}`}
                          >
                            {accelType.toUpperCase()}
                          </span>
                          <span className="resource-tag tag-spec">
                            {formatResourceSpecs(resource)}
                          </span>
                          {resource.metadata?.allowGitClone && (
                            <span className="resource-tag tag-git">
                              <i
                                className="fa fa-code-fork"
                                style={{ fontSize: "0.55rem" }}
                              ></i>{" "}
                              Git
                            </span>
                          )}
                        </div>
                      </a>
                    );
                  })}
                </div>
              </div>
            ))
          )}
        </section>
      </div>

      {/* Docs + News */}
      <div className="container">
        <section className="home-section" style={{ paddingTop: 0 }}>
          <div className="home-two-col">
            <div>
              <div className="home-section-header">
                <h2>Documentation</h2>
              </div>
              <div className="doc-list">
                <a
                  className="doc-item"
                  href="https://rocm.docs.amd.com/"
                  target="_blank"
                  rel="noopener"
                >
                  <div
                    className="doc-icon"
                    style={{ background: "#fce8e6", color: "#d93025" }}
                  >
                    <i className="fa fa-book"></i>
                  </div>
                  <div className="doc-text">
                    <h4>AMD ROCm Documentation</h4>
                    <p>Official ROCm platform docs &amp; API references</p>
                  </div>
                </a>
                <a
                  className="doc-item"
                  href="https://amdresearch.github.io/aup-learning-cloud/"
                  target="_blank"
                  rel="noopener"
                >
                  <div
                    className="doc-icon"
                    style={{ background: "#e8f0fe", color: "#1a73e8" }}
                  >
                    <i className="fa fa-laptop"></i>
                  </div>
                  <div className="doc-text">
                    <h4>AUP Learning Cloud User Guide</h4>
                    <p>Notebooks, terminals &amp; extensions</p>
                  </div>
                </a>
                <a
                  className="doc-item"
                  href="https://amdresearch.github.io/aup-learning-cloud/installation/single-node.html"
                  target="_blank"
                  rel="noopener"
                >
                  <div
                    className="doc-icon"
                    style={{ background: "#f3e8fd", color: "#9334e6" }}
                  >
                    <i className="fa fa-rocket"></i>
                  </div>
                  <div className="doc-text">
                    <h4>Platform Getting Started</h4>
                    <p>First-time user guide for AUP Learning Cloud setup</p>
                  </div>
                </a>
                <a
                  className="doc-item"
                  href="https://github.com/AMDResearch/aup-learning-cloud"
                  target="_blank"
                  rel="noopener"
                >
                  <div
                    className="doc-icon"
                    style={{ background: "#e6f4ea", color: "#1e8e3e" }}
                  >
                    <i className="fa fa-code-fork"></i>
                  </div>
                  <div className="doc-text">
                    <h4>AUP Learning Cloud GitHub Repository</h4>
                    <p>Clone &amp; launch your own AUP Learning Cloud</p>
                  </div>
                </a>
              </div>
            </div>
            <div>
              <div className="home-section-header">
                <h2>News &amp; Updates</h2>
              </div>
              <div className="news-list">
                {announcement && (
                  <div className="news-card">
                    <div className="news-meta">Announcement</div>
                    <h4>Platform Announcement</h4>
                    <p>{announcement}</p>
                  </div>
                )}
                <div className="news-card">
                  <div className="news-meta">Platform</div>
                  <h4>Welcome to AUP Learning Cloud</h4>
                  <p>
                    Get started with GPU-accelerated Jupyter notebooks powered
                    by AMD ROCm technology.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>

      {/* Footer */}
      <div className="home-footer">
        <div className="container">
          &copy; 2025–2026 Advanced Micro Devices, Inc. All rights reserved.
          &middot;
          AUP Learning Cloud
        </div>
      </div>

      {/* Stop Server Confirm Modal */}
      {/* Stop Server Confirm Modal */}
      {showStopConfirm && (
        <div className="confirm-overlay" onClick={() => setShowStopConfirm(false)}>
          <div className="confirm-modal" onClick={(e) => e.stopPropagation()}>
            <div className="confirm-icon">
              <i className="fa fa-exclamation-triangle"></i>
            </div>
            <h3>Stop Server?</h3>
            <p>Any unsaved work in your notebooks may be lost. Are you sure you want to stop?</p>
            <div className="confirm-actions">
              <button className="btn-home-sm" onClick={() => setShowStopConfirm(false)}>
                Cancel
              </button>
              <button className="btn-home-sm danger" onClick={doStop}>
                <i className="fa fa-stop"></i> Stop Server
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Usage Modal */}
      {showUsage && (
        <div className="confirm-overlay" onClick={() => setShowUsage(false)}>
          <div className="usage-modal" onClick={(e) => e.stopPropagation()}>
            <div className="usage-modal-header">
              <h3><i className="fa fa-bar-chart"></i> My Usage</h3>
              <button className="usage-close" onClick={() => setShowUsage(false)}>
                <i className="fa fa-times"></i>
              </button>
            </div>
            {usageLoading ? (
              <div className="usage-loading">
                <i className="fa fa-spinner fa-spin"></i> Loading usage data…
              </div>
            ) : !usageData ? (
              <div className="usage-loading">No usage data available yet.</div>
            ) : (
              <div className="usage-body">
                <div className="usage-stats-row">
                  <div className="usage-stat">
                    <div className="usage-stat-value">{formatMins(usageData.total_minutes)}</div>
                    <div className="usage-stat-label">Total Usage</div>
                  </div>
                  <div className="usage-stat">
                    <div className="usage-stat-value">{usageData.total_sessions}</div>
                    <div className="usage-stat-label">Sessions</div>
                  </div>
                  <div className="usage-stat">
                    <div className="usage-stat-value">
                      {usageData.total_sessions > 0
                        ? formatMins(Math.round(usageData.total_minutes / usageData.total_sessions))
                        : "—"}
                    </div>
                    <div className="usage-stat-label">Avg / Session</div>
                  </div>
                </div>

                {usageData.by_resource.length > 0 && (
                  <div className="usage-section">
                    <h4>By Resource</h4>
                    <div className="usage-resource-list">
                      {usageData.by_resource.map((r) => (
                        <div className="usage-resource-item" key={r.resource_type}>
                          <span className="usage-resource-name">
                            {r.resource_display ?? r.resource_type}
                          </span>
                          <span className="usage-resource-detail">
                            {formatMins(r.minutes)} · {r.sessions} sessions
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {usageData.recent_sessions.length > 0 && (
                  <div className="usage-section">
                    <h4>Recent Sessions</h4>
                    <div className="usage-sessions-list">
                      {usageData.recent_sessions.slice(0, 10).map((s, i) => (
                        <div className="usage-session-item" key={i}>
                          <div className="usage-session-name">
                            {s.resource_display ?? s.resource_type}
                            {s.accelerator_display && (
                              <span className="usage-session-accel"> · {s.accelerator_display}</span>
                            )}
                          </div>
                          <div className="usage-session-meta">
                            {s.start_time.slice(0, 16).replace("T", " ")}
                            {s.duration_minutes != null && ` · ${formatMins(s.duration_minutes)}`}
                            <span className={`usage-session-status ${s.status}`}>{s.status}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
