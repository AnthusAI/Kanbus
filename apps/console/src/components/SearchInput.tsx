import React from "react";
import { Search, X } from "lucide-react";

interface SearchInputProps {
  value: string;
  onChange: (value: string) => void;
  onClear: () => void;
  placeholder?: string;
}

export function SearchInput({
  value,
  onChange,
  onClear,
  placeholder = "Search..."
}: SearchInputProps) {
  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      event.currentTarget.blur();
    } else if (event.key === "Escape") {
      event.currentTarget.blur();
    }
  };

  const handleClearClick = () => {
    onClear();
  };

  const isActive = value.trim().length > 0;

  return (
    <div
      className={`search-input ${isActive ? "search-input--active" : ""}`}
      data-testid="search-input"
    >
      <Search className="search-icon" aria-hidden="true" />
      <input
        type="text"
        className="search-input-field"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        aria-label="Search issues"
        data-testid="search-input-field"
      />
      {value && (
        <button
          type="button"
          className="search-clear-button"
          onClick={handleClearClick}
          aria-label="Clear search"
          data-testid="search-clear-button"
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}
