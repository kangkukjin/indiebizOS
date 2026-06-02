/**
 * PhotoManager 공통 타입 정의
 */

export interface PhotoManagerProps {
  initialPath?: string | null;
}

export interface Scan {
  id: number;
  name: string;
  root_path: string;
  last_scan: string;
  photo_count: number;
  video_count: number;
  total_size_mb: number;
}

export interface MediaItem {
  id: number;
  path: string;
  filename: string;
  extension: string;
  size_mb: number;
  mtime: string;
  media_type: string;
  width: number | null;
  height: number | null;
  taken_date: string | null;
  camera: string | null;
  gps_lat?: number;
  gps_lon?: number;
  camera_make?: string;
  camera_model?: string;
}

export interface DuplicateGroup {
  hash: string;
  count: number;
  wasted_mb: number;
  files: MediaItem[];
}

export type ViewMode = 'gallery' | 'timeline' | 'duplicates' | 'stats' | 'map' | 'timemap';

export interface GpsPhoto {
  id: number;
  path: string;
  filename: string;
  lat: number;
  lon: number;
  taken_date: string | null;
  mtime: string | null;
}

// 브라우저에서 재생 가능한 동영상 확장자
export const BROWSER_PLAYABLE_VIDEO = ['mp4', 'webm', 'ogg', 'm4v', 'mov'];
