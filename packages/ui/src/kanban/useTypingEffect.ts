import { useState, useEffect, useRef } from "react";

/**
 * Hook that creates a typing/streaming effect for text content.
 * Text appears character by character over 420ms.
 *
 * @param text - The full text to display
 * @param enabled - Whether the typing effect is enabled
 * @returns The currently visible portion of the text
 */
export function useTypingEffect(text: string, enabled: boolean = true): string {
  const [displayedText, setDisplayedText] = useState(enabled ? "" : text);
  const previousTextRef = useRef(text);

  useEffect(() => {
    if (!enabled) {
      setDisplayedText(text);
      return;
    }

    // If text hasn't changed, don't re-animate
    if (previousTextRef.current === text) {
      setDisplayedText(text);
      return;
    }

    previousTextRef.current = text;

    // Reset and start typing animation
    setDisplayedText("");

    if (text.length === 0) return;

    const duration = 420; // Total duration in ms
    const charDelay = duration / text.length;
    let currentIndex = 0;

    const interval = setInterval(() => {
      currentIndex++;
      setDisplayedText(text.slice(0, currentIndex));

      if (currentIndex >= text.length) {
        clearInterval(interval);
      }
    }, charDelay);

    return () => clearInterval(interval);
  }, [text, enabled]);

  return displayedText;
}
