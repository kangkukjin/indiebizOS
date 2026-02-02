/**
 * MapView - 지도 뷰 컴포넌트
 */

import { useState, useEffect } from 'react';
import { MapPin } from 'lucide-react';
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';
import MarkerClusterGroup from 'react-leaflet-cluster';
import type { GpsPhoto } from './types';
import { createClusterCustomIcon } from './utils';
import 'leaflet/dist/leaflet.css';

interface MapViewProps {
  apiUrl: string;
  selectedPath: string | null;
  onSelectItem: (item: any, index: number, items: any[]) => void;
}

export function MapView({
  apiUrl,
  selectedPath,
  onSelectItem
}: MapViewProps) {
  const [gpsPhotos, setGpsPhotos] = useState<GpsPhoto[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!apiUrl || !selectedPath) return;

    const fetchGpsPhotos = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`${apiUrl}/photo/gps-photos?path=${encodeURIComponent(selectedPath)}`);
        const data = await res.json();
        if (data.success) {
          setGpsPhotos(data.items);
        } else {
          setError(data.error || '데이터를 불러올 수 없습니다');
        }
      } catch (e) {
        setError('서버 연결 실패');
      } finally {
        setLoading(false);
      }
    };

    fetchGpsPhotos();
  }, [apiUrl, selectedPath]);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-[#9B8B7A]">GPS 사진 로딩 중...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-red-500">{error}</div>
      </div>
    );
  }

  if (gpsPhotos.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <MapPin className="mx-auto text-5xl text-[#D4C8B8] mb-3" />
          <p className="text-[#9B8B7A]">위치 정보가 있는 사진이 없습니다</p>
        </div>
      </div>
    );
  }

  // 지도 중심 계산 (모든 사진의 평균 위치)
  const avgLat = gpsPhotos.reduce((sum, p) => sum + p.lat, 0) / gpsPhotos.length;
  const avgLon = gpsPhotos.reduce((sum, p) => sum + p.lon, 0) / gpsPhotos.length;

  return (
    <div className="flex-1 flex flex-col h-full">
      <div className="px-4 py-2 bg-[#F5F3F0] border-b border-[#E8E4DC] text-sm text-[#6B5D4D] flex-shrink-0">
        위치 정보가 있는 사진: {gpsPhotos.length}장
      </div>
      <div className="flex-1 relative">
        <MapContainer
          center={[avgLat, avgLon]}
          zoom={5}
          style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <MarkerClusterGroup
            chunkedLoading
            iconCreateFunction={createClusterCustomIcon}
            maxClusterRadius={80}
            spiderfyOnMaxZoom={true}
            showCoverageOnHover={false}
          >
            {gpsPhotos.map((photo) => (
              <Marker key={photo.id} position={[photo.lat, photo.lon]}>
                <Popup>
                  <div className="w-48">
                    <img
                      src={`${apiUrl}/photo/thumbnail?path=${encodeURIComponent(photo.path)}&size=150`}
                      alt={photo.filename}
                      className="w-full h-32 object-cover rounded mb-2 cursor-pointer"
                      onClick={() => {
                        const idx = gpsPhotos.findIndex(p => p.id === photo.id);
                        const items = gpsPhotos.map(p => ({
                          id: p.id,
                          path: p.path,
                          filename: p.filename,
                          media_type: 'photo',
                          gps_lat: p.lat,
                          gps_lon: p.lon,
                          taken_date: p.taken_date,
                          mtime: p.mtime
                        }));
                        onSelectItem(items[idx], idx, items);
                      }}
                    />
                    <p className="text-xs font-medium truncate">{photo.filename}</p>
                    {photo.taken_date && (
                      <p className="text-xs text-gray-500">
                        {new Date(photo.taken_date).toLocaleDateString()}
                      </p>
                    )}
                  </div>
                </Popup>
              </Marker>
            ))}
          </MarkerClusterGroup>
        </MapContainer>
      </div>
    </div>
  );
}
