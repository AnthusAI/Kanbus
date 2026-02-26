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
    title: "Intro to Kanbus",
    description: "A quick elevator pitch covering what Kanbus is, how files replace the database, why it's built for AI agents, and the three ways to use it.",
    filename: "intro.mp4",
    poster: "intro-poster.jpg"
  }
];

export const getVideoById = (id: string): VideoEntry | undefined =>
  VIDEOS.find((video) => video.id === id);
