/* Live flight map: Leaflet markers that glide between server updates. */
(function () {
  // Plane glyph pointing up (Material Design "flight" icon), rotated by heading.
  const PLANE = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z"/></svg>';

  const planes = new Map(); // id -> { marker, data }
  let map, cfg, receivedAt = 0, recenterTimer = null, selectedId = null;

  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const nowSec = () => performance.now() / 1000;

  function init(config) {
    cfg = config;
    const home = [cfg.home.lat, cfg.home.lon];
    map = L.map('map', {
      center: home, zoom: cfg.map_zoom, zoomSnap: 0.5, zoomControl: false,
      zoomAnimation: false, markerZoomAnimation: false,
    });
    const key = cfg.carto_key ? `?key=${encodeURIComponent(cfg.carto_key)}` : '';
    L.tileLayer(`https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png${key}`, {
      subdomains: 'abcd', maxZoom: 14,
      attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
    }).addTo(map);
    L.circle(home, { radius: cfg.radius_mi * 1609.34, color: '#7cc4ff', weight: 1, opacity: 0.45, dashArray: '4 10', fill: false, interactive: false }).addTo(map);
    L.circleMarker(home, { radius: 6, color: '#0c1420', weight: 2, fillColor: '#7cc4ff', fillOpacity: 1, interactive: false }).addTo(map);

    // Airports: hollow muted ring plus code label, in their own pane between the radius ring and the planes.
    map.createPane('airports');
    map.getPane('airports').style.zIndex = 450;
    map.getPane('airports').style.pointerEvents = 'none';
    for (const a of cfg.airports || []) {
      const at = [a.lat, a.lon];
      L.circleMarker(at, { pane: 'airports', radius: 5, color: '#8a9db2', weight: 2, fill: false, interactive: false }).addTo(map);
      L.marker(at, {
        pane: 'airports', interactive: false, keyboard: false,
        icon: L.divIcon({ className: 'airport-label', iconSize: [0, 0], html: `<span>${esc(a.iata)}</span>` }),
      }).addTo(map);
    }

    map.on('zoomstart', () => map.getContainer().classList.add('zooming'));
    map.on('zoomend', () => map.getContainer().classList.remove('zooming'));
    // After someone pans the map by touch, drift back to home so the display is never stuck.
    map.on('dragend', () => {
      clearTimeout(recenterTimer);
      recenterTimer = setTimeout(() => map.setView(home, cfg.map_zoom), 60000);
    });

    setInterval(tick, 1000);
    poll();
    setInterval(poll, cfg.client_poll_ms);
  }

  async function poll() {
    let data;
    try {
      const res = await fetch('/api/flights');
      data = await res.json();
    } catch (err) {
      data = { flights: [], error: 'Server not reachable', age_s: null };
    }
    receivedAt = nowSec() - (data.age_s || 0);
    sync(data.flights || []);
    renderBoard(data.flights || []);
    window.dispatchEvent(new CustomEvent('flights:update', { detail: data }));
  }

  // Estimate where a plane is now by projecting its last known position along its heading.
  function project(f, elapsed) {
    if (f.speed_kt == null || f.heading == null) return [f.lat, f.lon];
    const dist = f.speed_kt * 0.514444 * Math.min(elapsed, 90); // meters
    const th = (f.heading * Math.PI) / 180;
    const dLat = (dist * Math.cos(th)) / 111320;
    const dLon = (dist * Math.sin(th)) / (111320 * Math.cos((f.lat * Math.PI) / 180));
    return [f.lat + dLat, f.lon + dLon];
  }

  function tagText(f) {
    const name = [f.airline, f.flight_number].filter(Boolean).join(' ');
    let route;
    if (f.route_confidence === 'full') {
      const o = f.origin && (f.origin.iata || f.origin.icao);
      const d = f.destination && (f.destination.iata || f.destination.icao);
      route = `${o || '?'} \u2192 ${d || '?'}`;
    } else if (f.route_confidence === 'inferred') {
      const anchor = f.destination || f.origin;
      const code = anchor && (anchor.iata || anchor.icao);
      route = f.destination ? `to ${code}` : `from ${code}`;
    } else {
      route = altText(f);
    }
    return [name || f.callsign || f.icao24, route];
  }

  function altText(f) {
    return f.alt_ft == null ? 'altitude unknown' : `${(Math.round(f.alt_ft / 100) * 100).toLocaleString('en-US')} ft`;
  }

  function sync(flights) {
    const seen = new Set();
    for (const f of flights) {
      seen.add(f.icao24);
      let p = planes.get(f.icao24);
      if (!p) {
        const icon = L.divIcon({
          className: 'plane-wrap', iconSize: [0, 0],
          html: `<div class="plane"><div class="glyph">${PLANE}</div><div class="tag"><b></b><span></span></div></div>`,
        });
        const marker = L.marker(project(f, 0), { icon, keyboard: false }).addTo(map);
        marker.on('click', () => select(f.icao24));
        p = { marker, data: f };
        planes.set(f.icao24, p);
      }
      p.data = f;
      const el = p.marker.getElement();
      if (el) {
        el.querySelector('.glyph').style.transform = `rotate(${f.heading ?? 0}deg)`;
        const [line1, line2] = tagText(f);
        el.querySelector('.tag b').textContent = line1;
        el.querySelector('.tag span').textContent = line2;
        el.querySelector('.plane').classList.toggle('selected', f.icao24 === selectedId);
      }
    }
    for (const [id, p] of planes) {
      if (!seen.has(id)) { p.marker.remove(); planes.delete(id); }
    }
    tick();
  }

  function tick() {
    const elapsed = nowSec() - receivedAt;
    for (const p of planes.values()) p.marker.setLatLng(project(p.data, elapsed));
  }

  function select(id) {
    selectedId = id;
    const p = planes.get(id);
    if (p) map.panTo(p.marker.getLatLng());
    for (const [pid, q] of planes) {
      const el = q.marker.getElement();
      if (el) el.querySelector('.plane').classList.toggle('selected', pid === id);
    }
  }

  function trend(f) {
    if (f.vrate_fpm == null) return '';
    if (f.vrate_fpm > 300) return ', climbing';
    if (f.vrate_fpm < -300) return ', descending';
    return ', level';
  }

  function routeBlock(f) {
    if (f.route_confidence === 'full') {
      const o = f.origin || {}, d = f.destination || {};
      return `<div class="route"><span>${esc(o.iata || o.icao || '?')}</span><span class="to">to</span><span>${esc(d.iata || d.icao || '?')}</span></div>
              <div class="cities">${esc(o.city || '')}${o.city && d.city ? ' to ' : ''}${esc(d.city || '')}</div>`;
    }
    if (f.route_confidence === 'inferred') {
      const anchor = f.destination || f.origin;
      const verb = f.destination ? 'Arriving' : 'Departing';
      return `<div class="cities inferred">${esc(verb)} ${esc(anchor.city)}</div>`;
    }
    return `<div class="cities">${esc(f.aircraft_type || 'Route not available')}</div>`;
  }

  function renderBoard(flights) {
    const ol = document.getElementById('board-list');
    if (!flights.length) {
      ol.innerHTML = `<li class="empty">No aircraft within ${esc(cfg.radius_mi)} miles right now.</li>`;
      return;
    }
    ol.innerHTML = flights.slice(0, 7).map((f, i) => {
      const details = [f.aircraft_type, f.registered_owner].filter(Boolean).join(', ');
      return `<li class="row${i === 0 ? ' nearest' : ''}" data-id="${esc(f.icao24)}">
        <div class="top"><span class="num">${esc(f.flight_number)}</span><span class="air">${esc(f.airline || '')}</span></div>
        ${routeBlock(f)}
        <div class="meta">${details ? `${esc(details)}, ` : ''}${esc(altText(f))}${esc(trend(f))}, ${esc(f.speed_kt ?? '?')} kt, ${esc(f.distance_mi)} mi away</div>
      </li>`;
    }).join('');
    ol.querySelectorAll('.row').forEach((row) => row.addEventListener('click', () => select(row.dataset.id)));
  }

  window.FlightMap = { init };
})();
