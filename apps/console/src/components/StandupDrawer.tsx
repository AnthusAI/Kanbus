import React, { useCallback, useState } from "react";
import { createPortal } from "react-dom";
import {
  generateStandupReport,
  type StandupGenerateRequest,
  type StandupGenerateResponse,
  type StandupProfile,
  type StandupWindow,
} from "../api/client";

interface StandupDrawerProps {
  apiBase: string;
  isOpen: boolean;
  onClose: () => void;
}

type StandupWindowDefaults = {
  window: StandupWindow;
  lookback: string;
  skipWeekends: boolean;
};

const PROFILE_WINDOW_DEFAULTS: Record<StandupProfile, StandupWindowDefaults> = {
  "meeting-script": {
    window: "calendar",
    lookback: "24h",
    skipWeekends: true,
  },
  "director-brief": {
    window: "rolling",
    lookback: "24h",
    skipWeekends: false,
  },
};

function formatReportText(response: StandupGenerateResponse): string {
  if (response.text.trim().length > 0) {
    return response.text;
  }
  const lines: string[] = [`Standup (${response.profile})`];
  for (const section of response.sections) {
    lines.push("");
    lines.push(section.name);
    for (const bullet of section.bullets) {
      lines.push(`- ${bullet}`);
    }
  }
  lines.push("");
  return lines.join("\n");
}

function buildStandupRequest(
  profile: StandupProfile,
  window: StandupWindow,
  lookback: string,
  skipWeekends: boolean
): StandupGenerateRequest {
  const defaults = PROFILE_WINDOW_DEFAULTS[profile];
  const request: StandupGenerateRequest = { profile };
  if (window !== defaults.window) {
    request.window = window;
  }
  if (lookback !== defaults.lookback) {
    request.lookback = lookback;
  }
  if (skipWeekends !== defaults.skipWeekends) {
    request.skip_weekends = skipWeekends;
  }
  return request;
}

export function StandupDrawer({ apiBase, isOpen, onClose }: StandupDrawerProps) {
  const [profile, setProfile] = useState<StandupProfile>("meeting-script");
  const [window, setWindow] = useState<StandupWindow>(
    PROFILE_WINDOW_DEFAULTS["meeting-script"].window
  );
  const [lookback, setLookback] = useState(PROFILE_WINDOW_DEFAULTS["meeting-script"].lookback);
  const [skipWeekends, setSkipWeekends] = useState(
    PROFILE_WINDOW_DEFAULTS["meeting-script"].skipWeekends
  );
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reportText, setReportText] = useState<string | null>(null);
  const [reportSections, setReportSections] = useState<StandupGenerateResponse["sections"]>([]);
  const [copyStatus, setCopyStatus] = useState<string | null>(null);

  const resetResult = useCallback(() => {
    setError(null);
    setReportText(null);
    setReportSections([]);
    setCopyStatus(null);
  }, []);

  const applyProfileDefaults = useCallback((nextProfile: StandupProfile) => {
    const defaults = PROFILE_WINDOW_DEFAULTS[nextProfile];
    setWindow(defaults.window);
    setLookback(defaults.lookback);
    setSkipWeekends(defaults.skipWeekends);
  }, []);

  const handleGenerate = useCallback(async () => {
    resetResult();
    setIsGenerating(true);
    try {
      const response = await generateStandupReport(
        apiBase,
        buildStandupRequest(profile, window, lookback, skipWeekends)
      );
      setReportText(formatReportText(response));
      setReportSections(response.sections);
    } catch (generationError) {
      const message =
        generationError instanceof Error
          ? generationError.message
          : "standup generation failed";
      setError(message);
      setReportText(null);
      setReportSections([]);
    } finally {
      setIsGenerating(false);
    }
  }, [apiBase, profile, window, lookback, skipWeekends, resetResult]);

  const handleCopy = useCallback(async () => {
    if (!reportText) {
      return;
    }
    try {
      await navigator.clipboard.writeText(reportText);
      setCopyStatus("Copied");
    } catch {
      setCopyStatus("Copy failed");
    }
  }, [reportText]);

  if (!isOpen) {
    return null;
  }

  const drawer = (
    <div className="standup-drawer-backdrop" data-testid="standup-drawer-backdrop">
      <div
        className="standup-drawer"
        data-testid="standup-drawer"
        role="dialog"
        aria-modal="true"
        aria-label="Standup report"
      >
        <div className="standup-drawer-header">
          <h2 className="standup-drawer-title">Standup</h2>
          <button
            type="button"
            className="standup-drawer-close"
            data-testid="standup-drawer-close"
            onClick={onClose}
          >
            Close
          </button>
        </div>

        <div className="standup-drawer-controls">
          <label className="standup-profile-control">
            <span>Profile</span>
            <select
              data-testid="standup-profile-select"
              value={profile}
              onChange={(event) => {
                const nextProfile = event.target.value as StandupProfile;
                setProfile(nextProfile);
                applyProfileDefaults(nextProfile);
                resetResult();
              }}
              disabled={isGenerating}
            >
              <option value="meeting-script">meeting-script</option>
              <option value="director-brief">director-brief</option>
            </select>
          </label>
          <label className="standup-window-control">
            <span>Window</span>
            <select
              data-testid="standup-window-select"
              value={window}
              onChange={(event) => {
                setWindow(event.target.value as StandupWindow);
                resetResult();
              }}
              disabled={isGenerating}
            >
              <option value="rolling">rolling</option>
              <option value="calendar">calendar</option>
            </select>
          </label>
          <label className="standup-lookback-control">
            <span>Lookback</span>
            <input
              data-testid="standup-lookback-input"
              type="text"
              value={lookback}
              onChange={(event) => {
                setLookback(event.target.value);
                resetResult();
              }}
              disabled={isGenerating}
            />
          </label>
          <label className="standup-skip-weekends-control">
            <span>Skip weekends</span>
            <input
              data-testid="standup-skip-weekends-checkbox"
              type="checkbox"
              checked={skipWeekends}
              onChange={(event) => {
                setSkipWeekends(event.target.checked);
                resetResult();
              }}
              disabled={isGenerating}
            />
          </label>
          <button
            type="button"
            className="standup-generate-button"
            data-testid="standup-generate-button"
            onClick={() => {
              void handleGenerate();
            }}
            disabled={isGenerating}
          >
            {isGenerating ? "Generating..." : "Generate"}
          </button>
        </div>

        {isGenerating ? (
          <div className="standup-drawer-busy" data-testid="standup-drawer-busy">
            Generating standup report...
          </div>
        ) : null}

        {error ? (
          <div className="standup-drawer-error" data-testid="standup-drawer-error" role="alert">
            {error}
          </div>
        ) : null}

        {reportText ? (
          <div className="standup-drawer-result" data-testid="standup-drawer-result">
            <div className="standup-drawer-result-actions">
              <button
                type="button"
                className="standup-copy-button"
                data-testid="standup-copy-button"
                onClick={() => {
                  void handleCopy();
                }}
              >
                Copy
              </button>
              {copyStatus ? (
                <span className="standup-copy-status" data-testid="standup-copy-status">
                  {copyStatus}
                </span>
              ) : null}
            </div>
            <div className="standup-drawer-sections" data-testid="standup-drawer-sections">
              {reportSections.map((section) => (
                <section
                  key={section.name}
                  className="standup-drawer-section"
                  data-testid="standup-drawer-section"
                  data-section-name={section.name}
                >
                  <h3
                    className="standup-drawer-section-title"
                    data-testid="standup-drawer-section-title"
                  >
                    {section.name}
                  </h3>
                  {section.bullets.length > 0 ? (
                    <ul className="standup-drawer-section-bullets">
                      {section.bullets.map((bullet) => (
                        <li key={`${section.name}-${bullet}`}>{bullet}</li>
                      ))}
                    </ul>
                  ) : null}
                </section>
              ))}
            </div>
            <pre className="standup-drawer-text" data-testid="standup-drawer-text">
              {reportText}
            </pre>
          </div>
        ) : null}
      </div>
    </div>
  );

  return createPortal(drawer, document.body);
}
