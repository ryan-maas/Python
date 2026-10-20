/* Scene rotation, clock, and the calendar / stocks / weather panes. */
(async function () {
  // Edit this list to reorder, retime, or remove scenes. Seconds are how long each one stays up.
  const SCENES = [
    { id: 'map', label: 'Overhead', seconds: 60 },
    { id: 'calendar', label: 'Calendar', seconds: 20, load: loadCalendar },
    { id: 'stocks', label: 'Markets', seconds: 15, load: loadStocks },
    { id: 'news', label: 'News', seconds: 20, load: loadNews },
    { id: 'weather', label: 'Weather', seconds: 15, load: loadWeather },
  ];
  const TAP_DWELL = 90;   // seconds to stay on a scene after someone taps its tab
  const ALERT_DWELL = 45; // seconds to stay on the map after a plane comes close

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const getJSON = async (url) => (await fetch(url)).json();

  let cfg;
  try {
    cfg = await getJSON('/api/config');
  } catch (err) {
    document.body.innerHTML = '<p style="padding:2rem">Cannot reach the tracker server.</p>';
    return;
  }

  // ---- auto-reload after a deploy ----
  // Poll /api/version and reload when it changes. Failures are ignored (the
  // server may be restarting). The sessionStorage guard stops a reload loop.
  async function watchVersion() {
    const RELOAD_GUARD_MS = 30000;
    const fetchVersion = async () => (await getJSON('/api/version')).version;
    let known = null;
    try { known = await fetchVersion(); } catch (err) { /* record it on the next good poll */ }
    setInterval(async () => {
      let v;
      try { v = await fetchVersion(); } catch (err) { return; }
      if (!v) return;
      if (known === null) { known = v; return; }
      if (v === known) return;
      let last = 0;
      try { last = Number(sessionStorage.getItem('lastReload')) || 0; } catch (err) { /* storage unavailable */ }
      if (Date.now() - last < RELOAD_GUARD_MS) return;
      try { sessionStorage.setItem('lastReload', String(Date.now())); } catch (err) { /* storage unavailable */ }
      location.reload();
    }, cfg.version_poll_seconds * 1000);
  }
  if (cfg.auto_reload) watchVersion();

  const tz = cfg.timezone;
  const fmtTime = new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit', timeZone: tz });
  const fmtClockDate = new Intl.DateTimeFormat('en-US', { weekday: 'long', month: 'long', day: 'numeric', timeZone: tz });
  const fmtDay = new Intl.DateTimeFormat('en-US', { weekday: 'long', month: 'short', day: 'numeric', timeZone: tz });
  const fmtWeekday = new Intl.DateTimeFormat('en-US', { weekday: 'short', timeZone: 'UTC' });
  const dayKey = (d) => d.toLocaleDateString('en-CA', { timeZone: tz }); // YYYY-MM-DD

  // ---- clock ----
  function tickClock() {
    const now = new Date();
    $('time').textContent = fmtTime.format(now);
    $('date').textContent = fmtClockDate.format(now);
  }
  tickClock();
  setInterval(tickClock, 1000);

  // ---- rotation ----
  const tabs = SCENES.map((s, i) => {
    const b = document.createElement('button');
    b.textContent = s.label;
    b.addEventListener('click', () => show(i, TAP_DWELL));
    $('tabs').appendChild(b);
    return b;
  });
  let current = -1, timer = null;

  function schedule(seconds) {
    clearTimeout(timer);
    timer = setTimeout(() => show((current + 1) % SCENES.length), seconds * 1000);
  }

  function show(i, dwell) {
    if (i !== current) {
      current = i;
      SCENES.forEach((s, idx) => {
        $(`scene-${s.id}`).classList.toggle('active', idx === i);
        tabs[idx].classList.toggle('active', idx === i);
      });
      if (SCENES[i].load) SCENES[i].load();
    }
    schedule(dwell ?? SCENES[i].seconds);
  }

  // ---- flight status and close-plane alerts ----
  const alerted = new Set();
  window.addEventListener('flights:update', (e) => {
    const data = e.detail;
    const flights = data.flights || [];
    const dot = $('status-dot');
    if (!data.updated) {
      dot.className = data.error ? 'bad' : '';
      $('status-text').textContent = data.error ? 'Flight data unavailable' : 'Loading flights';
    } else if (data.age_s > 120) {
      dot.className = 'bad';
      $('status-text').textContent = 'Flight data is out of date';
    } else {
      dot.className = 'ok';
      $('status-text').textContent = `${flights.length} aircraft overhead`;
    }

    const near = flights.find((f) => f.distance_mi <= cfg.alert_mi && !alerted.has(f.icao24));
    if (near) {
      alerted.add(near.icao24);
      if (SCENES[current]?.id !== 'map') show(0, ALERT_DWELL);
    }
    if (alerted.size > 300) alerted.clear();
  });

  // ---- calendar ----
  async function loadCalendar() {
    const box = $('cal-body');
    try {
      const data = await getJSON('/api/calendar');
      if (data.error) { box.innerHTML = `<p class="note">${esc(data.error)}</p>`; return; }
      if (!data.events.length) { box.innerHTML = '<p class="note">Nothing on the calendar for the next week.</p>'; return; }

      const today = dayKey(new Date());
      const tomorrow = dayKey(new Date(Date.now() + 864e5));
      const groups = new Map();
      for (const ev of data.events.slice(0, 16)) {
        const start = new Date(ev.start);
        let key = dayKey(start);
        if (key < today) key = today; // multi-day events already underway
        if (!groups.has(key)) groups.set(key, { date: start, items: [] });
        groups.get(key).items.push({ ev, start });
      }
      box.innerHTML = [...groups].map(([key, g]) => {
        const label = key === today ? 'Today' : key === tomorrow ? 'Tomorrow' : fmtDay.format(g.date);
        const rows = g.items.map(({ ev, start }) => `
          <div class="ev">
            <span class="when">${ev.all_day ? 'All day' : esc(fmtTime.format(start))}</span>
            <span>${esc(ev.title)}${ev.location ? `<span class="where">${esc(ev.location)}</span>` : ''}</span>
          </div>`).join('');
        return `<section class="day"><h3 class="${key === today ? 'today' : ''}">${esc(label)}</h3>${rows}</section>`;
      }).join('');
    } catch (err) {
      box.innerHTML = '<p class="note">Could not load the calendar.</p>';
    }
  }

  // ---- stocks ----
  const signed = (n, digits = 2) => (n > 0 ? '+' : '') + n.toFixed(digits);
  async function loadStocks() {
    const box = $('stocks-body');
    try {
      const data = await getJSON('/api/stocks');
      if (data.error) { box.innerHTML = `<p class="note">${esc(data.error)}</p>`; return; }
      box.innerHTML = data.quotes.map((q) => {
        const dir = q.change > 0 ? 'up' : q.change < 0 ? 'down' : '';
        const chg = q.change == null ? '' : `${signed(q.change)} (${signed(q.percent)}%)`;
        return `<div class="quote">
          <span class="id">
            <span class="sym">${esc(q.symbol)}</span>
            <span class="name">${esc(q.name)}</span>
          </span>
          <span class="px">$${q.price.toFixed(2)}</span>
          <span class="chg ${dir}">${esc(chg)}</span>
        </div>`;
      }).join('');
    } catch (err) {
      box.innerHTML = '<p class="note">Could not load quotes.</p>';
    }
  }

  // ---- news ----
  function relTime(unixSeconds) {
    const mins = Math.round((Date.now() / 1000 - unixSeconds) / 60);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins} min ago`;
    const hours = Math.round(mins / 60);
    return `${hours} h ago`;
  }
  function newsColumn(heading, items) {
    if (!items.length) return `<div class="col"><h3>${esc(heading)}</h3><p class="note">No headlines.</p></div>`;
    const rows = items.map((it) => `
      <div class="headline">
        <div class="title">${esc(it.title)}</div>
        <div class="meta">${esc(it.source)} &middot; ${esc(relTime(it.published))}</div>
      </div>`).join('');
    return `<div class="col"><h3>${esc(heading)}</h3>${rows}</div>`;
  }
  async function loadNews() {
    const box = $('news-body');
    try {
      const data = await getJSON('/api/news');
      if (data.error) { box.innerHTML = `<p class="note">${esc(data.error)}</p>`; return; }
      if (!data.general.length && !data.markets.length) {
        box.innerHTML = '<p class="note">No headlines available.</p>';
        return;
      }
      box.innerHTML = newsColumn('Top stories', data.general) + newsColumn('Markets', data.markets);
    } catch (err) {
      box.innerHTML = '<p class="note">Could not load the news.</p>';
    }
  }

  // ---- weather ----
  // Hourly times come back as local wall-clock strings like "2026-10-02T15:00"
  // (already in cfg.timezone). Pull the hour out directly instead of going
  // through new Date(), which would reinterpret it in the browser's own zone.
  function hour12(timeStr) {
    const hour = parseInt(timeStr.slice(11, 13), 10);
    const period = hour < 12 ? 'AM' : 'PM';
    const h = hour % 12 === 0 ? 12 : hour % 12;
    return `${h} ${period}`;
  }
  async function loadWeather() {
    const box = $('weather-body');
    try {
      const data = await getJSON('/api/weather');
      if (data.error) { box.innerHTML = `<p class="note">${esc(data.error)}</p>`; return; }
      const c = data.current;
      const days = data.daily.map((d, i) => `
        <div class="day-col">
          <div class="name">${i === 0 ? 'Today' : esc(fmtWeekday.format(new Date(`${d.date}T12:00:00Z`)))}</div>
          <div class="hi">${esc(d.high)}\u00b0</div>
          <div class="lo">${esc(d.low)}\u00b0</div>
          <div class="desc">${esc(d.summary)}${d.rain_pct >= 20 ? `, ${esc(d.rain_pct)}% rain` : ''}</div>
        </div>`).join('');
      const hours = (data.hourly || []).length ? `
        <div class="hours">${data.hourly.map((h, i) => `
          <div class="hour-col">
            <div class="name">${i === 0 ? 'Now' : esc(hour12(h.time))}</div>
            <div class="temp">${esc(h.temp)}\u00b0</div>
            <div class="rain">${h.rain_pct != null && h.rain_pct >= 20 ? `${esc(h.rain_pct)}%` : ''}</div>
          </div>`).join('')}</div>` : '';
      box.innerHTML = `
        <div class="weather-top">
          <div class="now">
            <div class="temp">${esc(c.temp)}\u00b0</div>
            <div class="sum">${esc(c.summary)}</div>
            <div class="sub">Feels like ${esc(c.feels_like)}\u00b0, wind ${esc(c.wind_mph)} mph</div>
          </div>
          <div class="days">${days}</div>
        </div>
        ${hours}`;
    } catch (err) {
      box.innerHTML = '<p class="note">Could not load the weather.</p>';
    }
  }

  FlightMap.init(cfg);
  show(0);
})();
