import { useState, useEffect, useCallback } from "react";
import type { Resource, ResourceGroup } from "@auplc/shared";
import { getResources } from "@auplc/shared";

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
  const mem = req.memory.replace("Gi", "GB");
  let spec = `${req.cpu} CPU, ${mem}`;
  if (req["amd.com/gpu"]) spec += `, ${req["amd.com/gpu"]} GPU`;
  if (req["amd.com/npu"]) spec += `, ${req["amd.com/npu"]} NPU`;
  return spec;
}

function getAcceleratorType(r: Resource): "gpu" | "npu" | "cpu" {
  if (r.requirements["amd.com/gpu"]) return "gpu";
  if (r.requirements["amd.com/npu"]) return "npu";
  return "cpu";
}

function App() {
  const [serverActive, setServerActive] = useState(homeData.server_active);
  const [stopping, setStopping] = useState(false);
  const [announcement, setAnnouncement] = useState<string | null>(null);
  const [groups, setGroups] = useState<ResourceGroup[]>([]);
  const [resourcesLoading, setResourcesLoading] = useState(true);
  const [resourcesError, setResourcesError] = useState<string | null>(null);

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

  const handleStop = useCallback(
    async (e: React.MouseEvent) => {
      e.preventDefault();
      e.nativeEvent.stopImmediatePropagation();
      if (stopping) return;
      setStopping(true);
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
        }
      } catch (err) {
        console.error("Failed to stop server:", err);
      } finally {
        setStopping(false);
      }
    },
    [stopping],
  );

  const totalResources = groups.reduce(
    (sum, g) => sum + g.resources.length,
    0,
  );

  return (
    <div className="home-page">
      {/* Hero */}
      <section className="home-hero">
        <div className="container">
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
              {stopping
                ? "Stopping your server\u2026"
                : serverActive
                  ? 'Your server is running \u2014 click "My Server" to open JupyterLab'
                  : "Choose a resource below and launch your Jupyter environment"}
            </div>
          </div>
          <div className="lb-actions">
            {serverActive ? (
              <>
                <a
                  id="stop"
                  role="button"
                  className="btn-home-sm danger"
                  onClick={handleStop}
                >
                  <i
                    className={`fa ${stopping ? "fa-spinner fa-spin" : "fa-stop"}`}
                  ></i>{" "}
                  {stopping ? "Stopping\u2026" : "Stop My Server"}
                </a>
                <a
                  id="start"
                  role="button"
                  className="btn-launch"
                  href={homeData.server_url}
                >
                  <i className="fa fa-external-link"></i> My Server
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

      {/* Quick Start (compact strip) */}
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
            <a href={`${baseUrl}spawn`}>
              View all options{" "}
              <i
                className="fa fa-arrow-right"
                style={{ fontSize: "0.7rem" }}
              ></i>
            </a>
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
                        className="resource-card"
                        href={`${baseUrl}spawn?resource=${encodeURIComponent(resource.key)}`}
                        key={resource.key}
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
                    <p dangerouslySetInnerHTML={{ __html: announcement }} />
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
          &copy; 2025 Advanced Micro Devices, Inc. All rights reserved. &middot;
          AUP Learning Cloud
        </div>
      </div>
    </div>
  );
}

export default App;
