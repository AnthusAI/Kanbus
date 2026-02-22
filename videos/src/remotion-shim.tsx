import React from "react";

const getBabulus = () => {
  const babulus = (globalThis as any).Babulus;
  if (!babulus) {
    throw new Error("Babulus global not found. Ensure babulus-standard.js is loaded before custom components.");
  }
  return babulus;
};

export const useCurrentFrame = (): number => getBabulus().useCurrentFrame();

export const useVideoConfig = (): { fps: number; width: number; height: number; durationFrames: number } =>
  getBabulus().useVideoConfig();

export const spring = (...args: any[]) => getBabulus().spring(...args);

export const interpolate = (...args: any[]) => getBabulus().interpolate(...args);

export function getRemotionEnvironment() {
  return {
    isRendering: true,
    isRenderingOnServer: false
  };
}

export const Img: React.FC<React.ImgHTMLAttributes<HTMLImageElement>> = (props) => {
  return <img {...props} />;
};

export const staticFile = (path: string): string => path;

export const Audio: React.FC = () => null;

export const Sequence: React.FC<{ children?: React.ReactNode }> = ({ children }) => {
  return <>{children}</>;
};
