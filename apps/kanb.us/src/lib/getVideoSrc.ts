export const getVideosBaseUrl = (): string | null => {
  return process.env.GATSBY_VIDEOS_BASE_URL ?? null;
};

export const getVideoSrc = (filename: string): string => {
  const base = getVideosBaseUrl();
  if (!base) {
    throw new Error("GATSBY_VIDEOS_BASE_URL is required to resolve video URLs.");
  }
  return `${base.replace(/\/$/, "")}/${filename}`;
};
