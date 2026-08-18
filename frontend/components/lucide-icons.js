/**
 * Lucide Icons Loader — يحمّل أيقونات Lucide CDN ويوفّر دوال مساعدة
 * للإدراج في أي مكان في الواجهة. الأيقونات 24×24 SVG بتصميم احترافي.
 *
 * الاستخدام:
 *   lucideIcon('home')          → <svg>...</svg>
 *   lucideIcon('search', {size:20, stroke:2})
 */
(function () {
  const CDN = "https://unpkg.com/lucide@latest/dist/umd/lucide.min.js";
  const cache = new Map();

  // خريطة الأيقونات المُستخدمة في المشروع → اسم Lucide
  const ALIASES = {
    search: "search",
    home: "home",
    building: "building",
    map: "map-pin",
    chart: "bar-chart-3",
    trend: "trending-up",
    trendDown: "trending-down",
    star: "star",
    phone: "phone",
    mail: "mail",
    filter: "filter",
    download: "download",
    upload: "upload",
    share: "share-2",
    copy: "copy",
    check: "check",
    close: "x",
    plus: "plus",
    minus: "minus",
    arrow: "arrow-left",
    arrowUp: "arrow-up",
    arrowDown: "arrow-down",
    eye: "eye",
    eyeOff: "eye-off",
    refresh: "refresh-cw",
    settings: "settings",
    user: "user",
    users: "users",
    calendar: "calendar",
    clock: "clock",
    tag: "tag",
    dollarSign: "ruler",
    area: "maximize",
    mapPin: "map-pin",
    dollarCircle: "circle-dollar-sign",
    bell: "bell",
    bellOff: "bell-off",
    shield: "shield-check",
    lock: "lock",
    unlock: "unlock",
    globe: "globe",
    link: "external-link",
    whatsapp: "message-circle",
    file: "file-text",
    image: "image",
    camera: "camera",
    edit: "pencil",
    trash: "trash-2",
    save: "save",
    printer: "printer",
    clipboard: "clipboard",
    info: "info",
    alertTriangle: "alert-triangle",
    alertCircle: "alert-circle",
    chevronDown: "chevron-down",
    chevronUp: "chevron-up",
    chevronLeft: "chevron-left",
    chevronRight: "chevron-right",
    menu: "menu",
    grid: "grid-3x3",
    list: "list",
    table: "table-2",
    maximize: "maximize-2",
    minimize: "minimize-2",
    externalLink: "external-link",
    copyCheck: "copy-check",
    wallet: "wallet",
    banknote: "banknote",
    percentage: "percent",
    scale: "scale",
    homeType: "home",
    apartment: "building-2",
    land: "mountain",
    shop: "store",
    building4: "landmark",
    broker: "briefcase",
    direct: "user-check",
    office: "building-2",
    unknown: "help-circle",
    analytics: "bar-chart-3",
    insights: "line-chart",
    dashboard: "layout-dashboard",
    opportunities: "zap",
    developments: "newspaper",
    metrics: "book-open",
    whyFree: "heart",
    pdf: "file-down",
    json: "file-json",
    saveSearch: "bookmark",
    saved: "bookmark-check",
    account: "user-circle",
    closeCircle: "x-circle",
    checkCircle: "check-circle",
    dollar: "circle-dollar-sign",
    contract: "scroll-text",
    handshake: "handshake",
    key: "key",
    lockOpen: "lock-open",
    alertTriangle2: "triangle-alert",
    megaphone: "megaphone",
    radio: "radio",
    satellite: "satellite-dish",
    wifi: "wifi",
    wifiOff: "wifi-off",
    signal: "signal",
    battery: "battery-full",
    batteryLow: "battery-low",
    sun: "sun",
    moon: "moon",
    palette: "palette",
    theme: "palette",
    language: "languages",
    translate: "languages",
    searchSmall: "search",
    zoomIn: "zoom-in",
    zoomOut: "zoom-out",
    move: "move",
    drag: "grip-vertical",
    sort: "arrow-up-down",
    sortUp: "arrow-up",
    sortDown: "arrow-down",
    expand: "expand",
    collapse: "shrink",
    minimize2: "minimize",
    maximize2: "maximize",
    fullScreen: "maximize-2",
    exitFullScreen: "minimize-2",
    pin: "pin",
    unpin: "pin-off",
    bookmark: "bookmark",
    bookmarkCheck: "bookmark-check",
    flag: "flag",
    archive: "archive",
    inbox: "inbox",
    send: "send",
    reply: "reply",
    forward: "forward",
    heart: "heart",
    heartOff: "heart-off",
    starOff: "star-off",
    thumbsUp: "thumbs-up",
    thumbsDown: "thumbs-down",
    smile: "smile",
    frown: "frown",
    meh: "meh",
    party: "party-popper",
    rocket: "rocket",
    lightning: "zap",
    bolt: "zap",
    fire: "flame",
    flame: "flame",
    droplet: "droplet",
    cloud: "cloud",
    sunCloud: "cloud-sun",
    rain: "cloud-rain",
    snow: "snowflake",
    wind: "wind",
    thermometer: "thermometer",
    compass: "compass",
    anchor: "anchor",
    ship: "ship",
    plane: "plane",
    car: "car",
    bus: "bus",
    train: "train",
    bike: "bike",
    walk: "footprints",
    run: "person-standing",
    swim: "waves",
    gym: "dumbbell",
    yoga: "person-standing",
    play: "play",
    pause: "pause",
    stop: "square",
    skip: "skip-forward",
    volume: "volume-2",
    volumeOff: "volume-x",
    mic: "mic",
    micOff: "mic-off",
    camera2: "camera",
    video: "video",
    videoOff: "video-off",
    film: "film",
    music: "music",
    headphones: "headphones",
    speaker: "speaker",
    radio2: "radio",
    tv: "tv",
    monitor: "monitor",
    laptop: "laptop",
    tablet: "tablet",
    phone2: "smartphone",
    watch: "watch",
    clock2: "clock",
    alarm: "alarm-clock",
    timer: "timer",
    stopwatch: "stopwatch",
    calendar2: "calendar",
    calendarCheck: "calendar-check",
    calendarX: "calendar-x",
    calendarPlus: "calendar-plus",
    calendarMinus: "calendar-minus",
    mail2: "mail",
    mailOpen: "mail-open",
    send2: "send",
    inbox2: "inbox",
    draft: "file-edit",
    trash2: "trash-2",
    folder: "folder",
    folderOpen: "folder-open",
    file2: "file",
    fileText: "file-text",
    filePlus: "file-plus",
    fileMinus: "file-minus",
    fileX: "file-x",
    fileCheck: "file-check",
    fileWarning: "file-warning",
    fileInfo: "file-info",
    fileLock: "file-lock",
    fileKey: "file-key",
    fileSearch: "file-search",
    fileCode: "file-code",
    fileJson: "file-json-2",
    fileSpreadsheet: "file-spreadsheet",
    fileImage: "file-image",
    fileVideo: "file-video",
    fileAudio: "file-audio",
    fileArchive: "file-archive",
    fileDown: "file-down",
    fileUp: "file-up",
    fileRight: "file-right",
    fileLeft: "file-left",
  };

  function iconName(input) {
    return ALIASES[input] || input || "circle";
  }

  /**
   * إدراج أيقونة Lucide في عنصر DOM
   * @param {string} name - اسم الأيقونة (اسم Lucide أو من الخريطة)
   * @param {HTMLElement} el - العنصر الهدف
   * @param {object} opts - خيارات: {size, stroke, class}
   */
  function inject(name, el, opts = {}) {
    if (!el || !window.lucide) return;
    const svg = window.lucide.createElement(window.lucide.icons[iconName(name)]);
    if (!svg) return;
    const size = opts.size || 18;
    const stroke = opts.stroke || 1.8;
    svg.setAttribute("width", size);
    svg.setAttribute("height", size);
    svg.setAttribute("stroke-width", stroke);
    svg.style.verticalAlign = "middle";
    if (opts.class) svg.classList.add(opts.class);
    el.appendChild(svg);
    return svg;
  }

  /**
   * إنشاء سلسلة SVG جاهزة للاستخدام في innerHTML
   */
  function svgString(name, opts = {}) {
    const size = opts.size || 18;
    const stroke = opts.stroke || 1.8;
    const cls = opts.class || "";
    const color = opts.color || "currentColor";
    const i = iconName(name);
    // استخراج مسار SVG من Lucide
    const iconDef = window.lucide && window.lucide.icons && window.lucide.icons[i];
    if (!iconDef) return "";
    const el = window.lucide.createElement(iconDef);
    if (!el) return "";
    el.setAttribute("width", size);
    el.setAttribute("height", size);
    el.setAttribute("stroke-width", stroke);
    el.setAttribute("stroke", color);
    el.setAttribute("fill", "none");
    if (cls) el.setAttribute("class", cls);
    return el.outerHTML;
  }

  /**
   * استبدال جميع عناصر [data-lucide] في контينر
   */
  function replaceAll(container) {
    if (!window.lucide) return;
    (container || document).querySelectorAll("[data-lucide]").forEach((el) => {
      const name = el.getAttribute("data-lucide");
      const size = parseInt(el.getAttribute("data-lucide-size") || "18", 10);
      const stroke = parseFloat(el.getAttribute("data-lucide-stroke") || "1.8");
      const cls = el.getAttribute("data-lucide-class") || "";
      el.innerHTML = "";
      inject(name, el, { size, stroke, class: cls });
    });
  }

  // تحميل Lucide CDN
  function loadScript() {
    return new Promise((resolve) => {
      if (window.lucide) return resolve();
      if (document.querySelector(`script[src="${CDN}"]`)) {
        const check = setInterval(() => {
          if (window.lucide) { clearInterval(check); resolve(); }
        }, 50);
        return;
      }
      const s = document.createElement("script");
      s.src = CDN;
      s.onload = () => {
        // تأخير بسيط للتأكد من تهيئة Lucide
        setTimeout(resolve, 50);
      };
      s.onerror = () => resolve(); // لا نكسر الموقع إذا فشل التحميل
      document.head.appendChild(s);
    });
  }

  window.LucideIcons = { inject, svgString, replaceAll, iconName, loadScript };
})();
