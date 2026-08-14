import React, { useEffect, useState } from 'react';
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import { Map as MapIcon, Search } from 'lucide-react';
import api from '../services/api';
import './MapPage.css';

// Fix for default marker icon in react-leaflet
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});

const MapPage = () => {
  const [spots, setSpots] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  useEffect(() => {
    const fetchSpots = async () => {
      try {
        const response = await api.get('/spots/');
        const results = response.data.results || response.data;
        if (Array.isArray(results)) {
          setSpots(results);
        }
      } catch (error) {
        console.error('Failed to fetch spots', error);
      } finally {
        setLoading(false);
      }
    };
    fetchSpots();
  }, []);

  const filteredSpots = spots.filter(s => s.name.includes(search) || s.region.includes(search));
  
  // Default center (Seoul/Korea)
  const defaultCenter = [36.5, 127.5];

  return (
    <div className="map-page">
      <div className="map-header glass-panel">
        <h1><MapIcon className="inline-icon" /> 물따라 지도</h1>
        <div className="search-box">
          <Search size={18} className="search-icon" />
          <input 
            type="text" 
            placeholder="해수욕장, 계곡, 지역 검색..." 
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>
      
      <div className="map-container-wrapper glass-panel">
        {loading ? (
          <div className="flex-center" style={{ height: '100%' }}>지도 불러오는 중...</div>
        ) : (
          <MapContainer center={defaultCenter} zoom={7} style={{ height: '100%', width: '100%', borderRadius: '12px' }}>
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/">OpenStreetMap</a> contributors'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            {filteredSpots.map((spot) => (
              <Marker key={spot.id} position={[spot.lat, spot.lng]}>
                <Popup>
                  <div className="custom-popup">
                    <strong>{spot.name}</strong>
                    <p>{spot.region}</p>
                    <span className="badge">{spot.type}</span>
                  </div>
                </Popup>
              </Marker>
            ))}
          </MapContainer>
        )}
      </div>
    </div>
  );
};

export default MapPage;
