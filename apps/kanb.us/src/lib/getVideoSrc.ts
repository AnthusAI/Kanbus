export const getVideoSrc = (filename: string): string => {
  const base = process.env.GATSBY_VIDEOS_BASE_URL;
  if (!base) {
    throw new Error("GATSBY_VIDEOS_BASE_URL is required to resolve video URLs.");
  }
  return `${base.replace(/\/$/, "")}/${filename}`;
};
