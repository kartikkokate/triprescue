import { useEffect, useMemo } from "react";
import L from "leaflet";
import { Circle, MapContainer, Marker, Polyline, Popup, TileLayer, Tooltip, useMap } from "react-leaflet";
import type { PlaceInfo, TwinNode } from "../../types";
import { riskColor, pct } from "./format";

interface Props {
  nodes: TwinNode[];
  places: Record<string, PlaceInfo>;
  scenarioRain: Record<string, number>; // effective rain (mm/h) per place in the current scenario
  view: "local" | "route";
  selectedId: string | null;
  onSelect: (id: string) => void;
}

/** Fits the map to the trip: "local" = the place with the most bookings, "route" = everything. */
function FitTrip({ nodes, view }: { nodes: TwinNode[]; view: Props["view"] }) {
  const map = useMap();
  useEffect(() => {
    const pts: [number, number][] = [];
    const counts: Record<string, number> = {};
    nodes.forEach((n) => n.places.forEach((p) => (counts[p] = (counts[p] ?? 0) + 1)));
    const home = Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0];
    nodes.forEach((n) => {
      if (view === "local" && home && !n.places.includes(home)) return;
      if (n.lat != null && n.lon != null && (view === "route" || n.dest_lat == null)) pts.push([n.lat, n.lon]);
      if (view === "route" && n.dest_lat != null && n.dest_lon != null) pts.push([n.dest_lat, n.dest_lon]);
    });
    if (pts.length === 0) nodes.forEach((n) => n.lat != null && pts.push([n.lat!, n.lon!]));
    if (pts.length) map.flyToBounds(L.latLngBounds(pts).pad(view === "local" ? 0.6 : 0.2), { duration: 1.1, maxZoom: 12 });
  }, [view, nodes.length, map]);
  return null;
}

const markerIcon = (node: TwinNode, selected: boolean) => {
  const risk = node.p_broken + node.p_at_risk;
  const size = 14 + Math.round(risk * 14) + (selected ? 6 : 0);
  return L.divIcon({
    className: "",
    iconSize: [size, size],
    html: `<div class="twin-marker ${risk < 0.25 ? "calm" : ""}" style="width:${size}px;height:${size}px;background:${riskColor(risk)};color:${riskColor(risk)}"></div>`,
  });
};

export default function TwinMap({ nodes, places, scenarioRain, view, selectedId, onSelect }: Props) {
  // co-located bookings (hotel / beach activities) get a small spiral offset so all stay clickable
  const offsets = useMemo(() => {
    const seen: Record<string, number> = {};
    const out: Record<string, [number, number]> = {};
    nodes.forEach((n) => {
      if (n.lat == null || n.dest_lat != null) return;
      const k = `${n.lat.toFixed(2)},${n.lon!.toFixed(2)}`;
      const i = (seen[k] = (seen[k] ?? -1) + 1);
      out[n.id] = i === 0 ? [0, 0] : [0.004 * Math.cos(i * 2.1), 0.005 * Math.sin(i * 2.1)];
    });
    return out;
  }, [nodes]);

  return (
    <MapContainer center={[20.5, 78.9]} zoom={5} className="h-[440px] w-full rounded-card" scrollWheelZoom={false}>
      <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" />
      <FitTrip nodes={nodes} view={view} />

      {Object.entries(places).map(([name, p]) => {
        const rain = scenarioRain[name] ?? p.current?.rain_mm_h ?? 0;
        return (
          <Circle key={name} center={[p.lat, p.lon]} radius={6000 + rain * 900} pathOptions={{ color: "#228BE6", weight: 1, fillColor: "#56CCF2", fillOpacity: Math.min(0.4, 0.08 + rain / 120) }}>
            <Tooltip direction="top" className="twin-label" permanent>
              {name} · {rain.toFixed(1)} mm/h
            </Tooltip>
          </Circle>
        );
      })}

      {nodes
        .filter((n) => n.lat != null && n.dest_lat != null)
        .map((n) => (
          <Polyline
            key={`route-${n.id}`}
            positions={[[n.lat!, n.lon!], [n.dest_lat!, n.dest_lon!]]}
            pathOptions={{ color: riskColor(n.p_broken + n.p_at_risk), weight: n.type === "flight" ? 2.5 : 3.5, opacity: 0.9, className: "twin-route" }}
          />
        ))}

      {nodes
        .filter((n) => n.lat != null)
        .map((n) => {
          const [dy, dx] = offsets[n.id] ?? [0, 0];
          const pos: [number, number] = n.dest_lat != null ? [(n.lat! + n.dest_lat) / 2, (n.lon! + n.dest_lon!) / 2] : [n.lat! + dy, n.lon! + dx];
          return (
            <Marker key={n.id} position={pos} icon={markerIcon(n, n.id === selectedId)} eventHandlers={{ click: () => onSelect(n.id) }}>
              <Popup>
                <div className="text-xs space-y-1 min-w-[190px]">
                  <p className="font-semibold text-[13px]">{n.title}</p>
                  <p>Broken {pct(n.p_broken)} · At risk {pct(n.p_at_risk)}</p>
                  <p>Delay p50 {n.delay_p50.toFixed(0)} min · p90 {n.delay_p90.toFixed(0)} min</p>
                  <p className="text-slate-500">
                    {(n.weather.rain_mm_h ?? 0).toFixed(1)} mm/h · {(n.weather.wind_kmh ?? 0).toFixed(0)} km/h · {(n.weather.temp_c ?? 0).toFixed(0)}°C
                  </p>
                </div>
              </Popup>
            </Marker>
          );
        })}
    </MapContainer>
  );
}
