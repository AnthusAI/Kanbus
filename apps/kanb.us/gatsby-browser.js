import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-sans/700.css";
import "@fontsource/space-grotesk/400.css";
import "@fontsource/space-grotesk/500.css";
import "@fontsource/space-grotesk/600.css";
import "@kanbus/ui/styles/index.css"; /* Import shared UI base styles first */
import "./src/styles/global.css";

const syncSystemTheme = () => {
  try {
    const isDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const root = document.documentElement;
    if (isDark) {
      root.classList.add("dark");
      root.classList.remove("light");
    } else {
      root.classList.add("light");
      root.classList.remove("dark");
    }
  } catch (e) {}
};

export const onInitialClientRender = () => {
  syncSystemTheme();
  try {
    // Remove old manual storage if any
    localStorage.removeItem("theme");
    
    // Listen for OS theme changes
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", syncSystemTheme);
    
    // In case Gatsby's router strips the class on hydration, force it back
    const observer = new MutationObserver(() => {
      const isDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      const root = document.documentElement;
      const shouldHaveDark = isDark;
      const hasDark = root.classList.contains("dark");
      
      if (shouldHaveDark && !hasDark) {
        root.classList.add("dark");
        root.classList.remove("light");
      } else if (!shouldHaveDark && hasDark) {
        root.classList.add("light");
        root.classList.remove("dark");
      }
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  } catch (e) {}
};

export const onRouteUpdate = () => {
  syncSystemTheme();
};
