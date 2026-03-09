export const getMkDocsBaseUrl = (): string | null => {
  return process.env.GATSBY_MKDOCS_BASE_URL ?? null;
};

export const getMkDocsDocUrl = (slug: string): string | null => {
  const base = getMkDocsBaseUrl();
  if (!base) return null;

  const trimmedBase = base.replace(/\/$/, "");
  const trimmedSlug = slug.replace(/^\//, "").replace(/\/$/, "");
  return `${trimmedBase}/${trimmedSlug}/`;
};

export const getGitHubDocsSourceUrl = (repoPath: string): string => {
  const trimmed = repoPath.replace(/^\//, "");
  return `https://github.com/AnthusAI/Kanbus/blob/main/${trimmed}`;
};

