export const getVideoSrc = (filename: string): string => {
  const base = process.env.GATSBY_VIDEOS_BASE_URL;
  if (base && typeof base === "string") {
    return `${base.replace(/\/$/, "")}/${filename}`;
  }
  return `/videos/${filename}`;
};
