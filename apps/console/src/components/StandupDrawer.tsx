import React, { useCallback, useState } from "react";
import { generateStandupReport, type StandupGenerateResponse } from "../api/client";

export type StandupProfile = "meeting-script" | "director-brief";

interface StandupDrawerProps {
  apiBase: string;
  isOpen: boolean;
  onClose: () => void;
}

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

export function StandupDrawer({ apiBase, isOpen, onClose }: StandupDrawerProps) {
  const [profile, setProfile] = useState<StandupProfile>("meeting-script");
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

  const handleGenerate = useCallback(async () => {
    resetResult();
    setIsGenerating(true);
    try {
      const response = await generateStandupReport(apiBase, profile);
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
  }, [apiBase, profile, resetResult]);

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

  return (
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
                setProfile(event.target.value as StandupProfile);
                resetResult();
              }}
              disabled={isGenerating}
            >
              <option value="meeting-script">meeting-script</option>
              <option value="director-brief">director-brief</option>
            </select>
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
}
