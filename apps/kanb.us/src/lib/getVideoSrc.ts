export const getVideosBaseUrl = (): string | null => {
  return process.env.GATSBY_VIDEOS_BASE_URL ?? null;
};

export const getVideoSrc = (filename: string): string => {
  const base = getVideosBaseUrl();
  if (base) {
    return `${base.replace(/\/$/, "")}/${filename}`;
  }
  return `/videos/${filename}`;
};
