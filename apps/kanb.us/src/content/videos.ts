export type VideoEntry = {
  id: string;
  title: string;
  description: string;
  filename: string;
  poster?: string;
};

export const VIDEOS: VideoEntry[] = [
  {
    id: "intro",
    title: "Intro to Canvas",
    description: "What Canvas is and how it connects issues, plans, and execution.",
    filename: "intro.mp4",
    poster: "intro-poster.jpg"
  }
];

export const getVideoById = (id: string): VideoEntry | undefined =>
  VIDEOS.find((video) => video.id === id);
