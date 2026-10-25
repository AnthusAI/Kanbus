import type { NavAction, RouteContext, ViewMode } from "../types/console";
import { loadStoredViewMode } from "./ui-preferences-storage";

export function parseQueryParams(search: string): {
  search: string | null;
  focused: string | null;
  comment: string | null;
  typeFilter: string | null;
} {
  const params = new URLSearchParams(search);
  const searchParam = params.get("search");
  const focusedParam = params.get("focused");
  const commentParam = params.get("comment");
  const typeParam = params.get("type");
  return {
    search: searchParam && searchParam.length > 0 ? searchParam : null,
    focused: focusedParam && focusedParam.length > 0 ? focusedParam : null,
    comment: commentParam && commentParam.length > 0 ? commentParam : null,
    typeFilter: typeParam === "all" || typeParam?.startsWith("type:") ? typeParam : null,
  };
}

export function parseRoute(pathname: string, queryString?: string): RouteContext {
  const qp = parseQueryParams(queryString ?? window.location.search);
  const segments = pathname.split("/").filter(Boolean);
  const isStageName = (value: string | undefined): boolean =>
    value === "dev" || value === "prod" || value === "staging";
  if (segments[segments.length - 1] === "index.html") {
    segments.pop();
  }
  const viewModes: ViewMode[] = ["initiatives", "epics", "issues"];
  const isLocal =
    segments.length === 0
    || (segments[0] && viewModes.includes(segments[0] as ViewMode))
    || (segments[0] === "wiki");
  if (isLocal) {
    const rest = segments;
    if (rest.length === 0) {
      return {
        account: null,
        project: null,
        basePath: "",
        viewMode: loadStoredViewMode(),
        issueId: null,
        parentId: null,
        wikiPath: null,
        ...qp,
        error: null
      };
    }
    const head = rest[0];
    if (head === "wiki") {
      const wikiPathRaw = rest.slice(1).join("/");
      const wikiPath = wikiPathRaw ? decodeURIComponent(wikiPathRaw) : "";
      return {
        account: null,
        project: null,
        basePath: "",
        viewMode: null,
        issueId: null,
        parentId: null,
        wikiPath,
        ...qp,
        error: null
      };
    }
    if (head === "initiatives" || head === "epics" || head === "issues") {
      if (rest.length === 1) {
        return {
          account: null,
          project: null,
          basePath: "",
          viewMode: head,
          issueId: null,
          parentId: null,
          wikiPath: null,
          ...qp,
          error: null
        };
      }
    }
    if (head === "issues") {
      if (rest.length === 2) {
        return {
          account: null,
          project: null,
          basePath: "",
          viewMode: null,
          issueId: rest[1],
          parentId: null,
          wikiPath: null,
          ...qp,
          error: null
        };
      }
      if (rest.length === 3 && rest[2] === "all") {
        return {
          account: null,
          project: null,
          basePath: "",
          viewMode: null,
          issueId: null,
          parentId: rest[1],
          wikiPath: null,
          ...qp,
          error: null
        };
      }
      if (rest.length === 3) {
        return {
          account: null,
          project: null,
          basePath: "",
          viewMode: null,
          issueId: rest[2],
          parentId: rest[1],
          wikiPath: null,
          ...qp,
          error: null
        };
      }
    }
    return {
      account: null,
      project: null,
      basePath: "",
      viewMode: null,
      issueId: null,
      parentId: null,
      wikiPath: null,
      search: null,
      focused: null,
      comment: null,
      typeFilter: null,
      error: "Unsupported console route"
    };
  }
  if (segments.length === 1 && isStageName(segments[0])) {
    return {
      account: null,
      project: null,
      basePath: `/${segments[0]}`,
      viewMode: null,
      issueId: null,
      parentId: null,
      wikiPath: null,
      ...qp,
      error: null
    };
  }
  const hasStagePrefix =
    segments.length >= 3
    && isStageName(segments[0]);
  const tenantOffset = hasStagePrefix ? 1 : 0;

  if (segments.length < tenantOffset + 2) {
    return {
      account: null,
      project: null,
      basePath: null,
      viewMode: null,
      issueId: null,
      parentId: null,
      wikiPath: null,
      search: null,
      focused: null,
      comment: null,
      typeFilter: null,
      error: "URL must include /:account/:project"
    };
  }
  const account = segments[tenantOffset];
  const project = segments[tenantOffset + 1];
  const stagePrefix = hasStagePrefix ? `/${segments[0]}` : "";
  const basePath = `${stagePrefix}/${account}/${project}`;
  const rest = segments.slice(tenantOffset + 2);
  if (rest.length === 0) {
    return {
      account,
      project,
      basePath,
      viewMode: loadStoredViewMode(),
      issueId: null,
      parentId: null,
      wikiPath: null,
      ...qp,
      error: null
    };
  }
  const head = rest[0];
  if (head === "wiki") {
    const wikiPathRaw = rest.slice(1).join("/");
    const wikiPath = wikiPathRaw ? decodeURIComponent(wikiPathRaw) : "";
    return {
      account,
      project,
      basePath,
      viewMode: null,
      issueId: null,
      parentId: null,
      wikiPath,
      ...qp,
      error: null
    };
  }
  if (head === "initiatives" || head === "epics" || head === "issues") {
    if (rest.length === 1) {
      return {
        account,
        project,
        basePath,
        viewMode: head,
        issueId: null,
        parentId: null,
        wikiPath: null,
        ...qp,
        error: null
      };
    }
  }
  if (head === "issues") {
    if (rest.length === 2) {
      return {
        account,
        project,
        basePath,
        viewMode: null,
        issueId: rest[1],
        parentId: null,
        wikiPath: null,
        ...qp,
        error: null
      };
    }
    if (rest.length === 3 && rest[2] === "all") {
      return {
        account,
        project,
        basePath,
        viewMode: null,
        issueId: null,
        parentId: rest[1],
        wikiPath: null,
        ...qp,
        error: null
      };
    }
    if (rest.length === 3) {
      return {
        account,
        project,
        basePath,
        viewMode: null,
        issueId: rest[2],
        parentId: rest[1],
        wikiPath: null,
        ...qp,
        error: null
      };
    }
  }
  return {
    account,
    project,
    basePath,
    viewMode: null,
    issueId: null,
    parentId: null,
    wikiPath: null,
    search: null,
    focused: null,
    comment: null,
    typeFilter: null,
    error: "Unsupported console route"
  };
}

export function buildUrl(
  path: string,
  params: {
    search?: string | null;
    focused?: string | null;
    comment?: string | null;
    typeFilter?: string | null;
  } = {}
): string {
  const qp = new URLSearchParams();
  if (params.focused) {
    qp.set("focused", params.focused);
  }
  if (params.search) {
    qp.set("search", params.search);
  }
  if (params.comment) {
    qp.set("comment", params.comment);
  }
  if (params.typeFilter) {
    qp.set("type", params.typeFilter);
  }
  const qs = qp.toString();
  return qs ? `${path}?${qs}` : path;
}

export function navigate(
  path: string,
  setRoute: (route: RouteContext) => void,
  navActionRef?: { current: NavAction }
) {
  const url = new URL(path, window.location.href);
  window.history.pushState({}, "", url.pathname + url.search);
  if (navActionRef) {
    navActionRef.current = "push";
  }
  setRoute(parseRoute(url.pathname, url.search));
}

export function replaceCurrentRoute(
  params: {
    search?: string | null;
    focused?: string | null;
    comment?: string | null;
    typeFilter?: string | null;
  },
  setRoute: (route: RouteContext) => void
) {
  const url = buildUrl(window.location.pathname, params);
  const parsed = new URL(url, window.location.href);
  window.history.replaceState({}, "", parsed.pathname + parsed.search);
  setRoute(parseRoute(parsed.pathname, parsed.search));
}
