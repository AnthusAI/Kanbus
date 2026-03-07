export interface WikiPagesResponse {
  pages: string[];
}

export interface WikiPageResponse {
  path: string;
  content: string;
  exists: boolean;
}

export interface WikiCreateRequest {
  path: string;
  content?: string;
  overwrite?: boolean;
}

export interface WikiCreateResponse {
  path: string;
  created: boolean;
}

export interface WikiUpdateRequest {
  path: string;
  content: string;
}

export interface WikiUpdateResponse {
  path: string;
  updated: boolean;
}

export interface WikiRenameRequest {
  from_path: string;
  to_path: string;
  overwrite?: boolean;
}

export interface WikiRenameResponse {
  from_path: string;
  to_path: string;
  renamed: boolean;
}

export interface WikiDeleteResponse {
  path: string;
  deleted: boolean;
}

export interface WikiRenderRequest {
  path: string;
  content?: string;
}

export interface WikiRenderResponse {
  path: string;
  rendered_markdown: string;
}
