import React from "react";
import { Folder, FileText } from "lucide-react";

interface WikiDirectoryListingProps {
  path: string;
  entries: { name: string; path: string; isDir: boolean }[];
  onNavigate: (path: string) => void;
}

export function WikiDirectoryListing({
  path,
  entries,
  onNavigate
}: WikiDirectoryListingProps) {
  return (
    <div className="wiki-directory-listing">
      <div className="text-xl font-bold mb-6 text-foreground">
        {path === "" ? "Wiki Home" : `Index of ${path}`}
      </div>
      
      {entries.length === 0 ? (
        <div className="text-muted text-sm italic">This directory is empty.</div>
      ) : (
        <div className="grid gap-2">
          {entries.map((entry) => (
            <button
              key={entry.path}
              type="button"
              className="flex items-center gap-3 w-full text-left rounded-lg px-3 py-2 text-sm transition-colors hover:bg-[var(--background)] text-foreground group"
              onClick={() => onNavigate(entry.path)}
            >
              {entry.isDir ? (
                <Folder className="w-4 h-4 text-muted group-hover:text-foreground transition-colors" />
              ) : (
                <FileText className="w-4 h-4 text-muted group-hover:text-foreground transition-colors" />
              )}
              <span className="flex-1">{entry.name}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
