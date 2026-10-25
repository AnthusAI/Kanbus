import { useEffect, useRef, useState, type MutableRefObject, type Dispatch, type SetStateAction } from "react";
import type { NavAction, RouteContext } from "../types/console";
import { parseRoute } from "../utils/console-route";

export type ConsoleRouteState = {
  route: RouteContext;
  setRoute: Dispatch<SetStateAction<RouteContext>>;
  navActionRef: MutableRefObject<NavAction>;
};

export function useConsoleRoute(): ConsoleRouteState {
  const [route, setRoute] = useState<RouteContext>(() =>
    parseRoute(window.location.pathname, window.location.search)
  );
  const navActionRef = useRef<NavAction>("none");

  useEffect(() => {
    const handlePop = () => {
      navActionRef.current = "pop";
      setRoute(parseRoute(window.location.pathname, window.location.search));
    };
    window.addEventListener("popstate", handlePop);
    return () => window.removeEventListener("popstate", handlePop);
  }, []);

  useEffect(() => {
    const parsed = parseRoute(window.location.pathname, window.location.search);
    if (
      parsed.basePath !== route.basePath
      || parsed.issueId !== route.issueId
      || parsed.parentId !== route.parentId
      || parsed.wikiPath !== route.wikiPath
      || parsed.viewMode !== route.viewMode
      || parsed.search !== route.search
      || parsed.focused !== route.focused
      || parsed.comment !== route.comment
      || parsed.typeFilter !== route.typeFilter
      || parsed.error !== route.error
    ) {
      setRoute(parsed);
    }
  }, [route]);

  return { route, setRoute, navActionRef };
}
