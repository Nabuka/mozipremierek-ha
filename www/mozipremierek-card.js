class MozipremierekCard extends HTMLElement {
  setConfig(config) {
    this._config = config;
  }

  set hass(hass) {
    this._hass = hass;

    if (!this.content) {
      this.innerHTML = `
        <ha-card>
          <div id="card-body" class="card-body"></div>
        </ha-card>
        <style>
          .card-body {
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 28px;
          }
          .section-title {
            font-size: 1.3em;
            font-weight: 700;
            color: var(--primary-text-color, #fff);
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 8px;
            border-bottom: 2px solid var(--divider-color, rgba(255, 255, 255, 0.1));
            padding-bottom: 6px;
          }
          .movie-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
            gap: 20px;
          }
          .movie-card {
            position: relative;
            display: flex;
            flex-direction: column;
            background: var(--ha-card-background, var(--card-background-color, #1e1e1e));
            border-radius: 14px;
            overflow: hidden;
            border: 1px solid var(--divider-color, rgba(255, 255, 255, 0.12));
            transition: transform 0.25s ease, box-shadow 0.25s ease;
            cursor: pointer;
          }
          .movie-card:hover {
            transform: translateY(-6px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.5);
          }
          .movie-card:focus {
            outline: 2px solid var(--primary-color, #03a9f4);
            outline-offset: 2px;
          }
          .movie-card:focus:not(:focus-visible) {
            outline: none;
          }
          .poster-container {
            position: relative;
            width: 100%;
            aspect-ratio: 2 / 3;
            background: #000;
            overflow: hidden;
          }
          .poster-img {
            width: 100%;
            height: 100%;
            object-fit: cover;
          }
          .clapper-badge {
            position: absolute;
            top: 12px;
            right: 12px;
            background: rgba(0, 0, 0, 0.85);
            backdrop-filter: blur(6px);
            color: #fff;
            border-radius: 50%;
            width: 52px;
            height: 52px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 26px;
            z-index: 10;
            border: 1.5px solid rgba(255, 255, 255, 0.3);
            box-shadow: 0 4px 10px rgba(0,0,0,0.6);
            transition: transform 0.2s ease, background 0.2s ease;
          }
          .clapper-badge:hover {
            background: #e50914;
            transform: scale(1.15);
          }
          .platform-badge {
            position: absolute;
            bottom: 12px;
            left: 12px;
            padding: 6px 14px;
            border-radius: 8px;
            font-weight: 700;
            font-size: 0.9em;
            color: #fff;
            text-shadow: 0 1px 3px rgba(0,0,0,0.9);
            box-shadow: 0 4px 10px rgba(0,0,0,0.5);
            z-index: 4;
            letter-spacing: 0.5px;
          }
          .movie-info {
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 8px;
            flex-grow: 1;
            justify-content: space-between;
          }
          .movie-title {
            font-weight: 700;
            font-size: 1.3em;
            color: var(--primary-text-color, #fff);
            line-height: 1.35;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
          }
          .movie-date {
            font-size: 1.05em;
            color: var(--secondary-text-color, #aaa);
            font-weight: 500;
          }
          .mp-loading-text {
            padding: 16px;
            color: var(--secondary-text-color, #aaa);
          }
        </style>
      `;

      this.content = this.querySelector('#card-body');
      this.sortedMoviesData = {};

      this.content.addEventListener('click', (e) => {
        const card = e.target.closest('.movie-card');
        if (card) {
          this.openMovieFromCard(card);
        }
      });

      // Billentyűzetes elérhetőség: Enter / Space aktiválja a fókuszban lévő kártyát
      this.content.addEventListener('keydown', (e) => {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        const card = e.target.closest('.movie-card');
        if (card) {
          e.preventDefault();
          this.openMovieFromCard(card);
        }
      });

      this.loadMovies();
    }
  }

  openMovieFromCard(card) {
    const index = card.getAttribute('data-index');
    const category = card.getAttribute('data-category');
    const movie = this.sortedMoviesData?.[category]?.[index];
    if (movie) {
      this.openDetailModal(movie);
    }
  }

  // Egyszerű HTML-escapelés minden scrapelt/külső szöveghez, mielőtt innerHTML-be
  // kerülne - így egy "&", "<" vagy ehhez hasonló karakter a filmcímben/leírásban
  // nem törheti el a kártya megjelenítését, és nem is fecskendezhető be HTML/script.
  escapeHtml(value) {
    if (value === null || value === undefined) return '';
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // A platform badge/pill szín+név kiszámítása korábban 3 helyen volt szó
  // szerint duplikálva (rács nézet, modal pill) - egy helyre szervezve.
  getPlatformInfo(movie) {
    if (movie.platform) {
      return {
        bg: movie.platform.color || '#333',
        name: movie.platform.name || 'Streaming'
      };
    }
    return { bg: '#333', name: 'Streaming' };
  }

  getYouTubeId(url) {
    if (!url) return null;
    const regExp = /^.*(youtu.be\/|v\/|u\/\w\/|embed\/|watch\?v=|\&v=)([^#\&\?]*).*/;
    const match = url.match(regExp);
    return (match && match[2].length === 11) ? match[2] : null;
  }

  parseDateValue(dateStr) {
    if (!dateStr || dateStr === 'Premier' || dateStr === 'Hamarosan') return 99999999;
    const matchIso = dateStr.match(/(\d{4})\.(\d{2})\.(\d{2})/);
    if (matchIso) {
      return parseInt(`${matchIso[1]}${matchIso[2]}${matchIso[3]}`);
    }
    const months = {
      'január': '01', 'február': '02', 'március': '03', 'április': '04',
      'május': '05', 'június': '06', 'július': '07', 'augusztus': '08',
      'szeptember': '09', 'október': '10', 'november': '11', 'december': '12'
    };
    let lower = dateStr.toLowerCase();
    // Dinamikus alapértelmezett év a hardcodolt "2026" helyett - így a kártya
    // évváltás után is helyesen rendezi az év nélküli dátumokat.
    let year = String(new Date().getFullYear());
    let yearMatch = lower.match(/(\d{4})/);
    if (yearMatch) year = yearMatch[1];

    let month = '99';
    for (let m in months) {
      if (lower.includes(m)) {
        month = months[m];
        break;
      }
    }
    let dayMatch = lower.match(/(\d{1,2})\.?$/) || lower.match(/\s(\d{1,2})\.?\s/);
    let day = '99';
    if (dayMatch) {
      day = dayMatch[1].padStart(2, '0');
    }
    return parseInt(`${year}${month}${day}`);
  }

  sortMoviesByDate(movies) {
    return [...movies].sort((a, b) => this.parseDateValue(a.date) - this.parseDateValue(b.date));
  }

  createDetailModal() {
    let overlay = document.getElementById('mp-detail-overlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'mp-detail-overlay';
      overlay.innerHTML = `
        <style>
          #mp-detail-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            background: rgba(0, 0, 0, 0.88);
            backdrop-filter: blur(10px);
            z-index: 99999;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 12px;
            box-sizing: border-box;
          }
          #mp-detail-overlay.hidden {
            display: none !important;
          }
          .mp-modal-container {
            width: 100%;
            max-width: 900px;
            max-height: 92vh;
            background: #1c1c1e;
            color: #fff;
            border-radius: 16px;
            border: 1px solid rgba(255, 255, 255, 0.15);
            display: flex;
            flex-direction: column;
            overflow: hidden;
            box-shadow: 0 30px 60px rgba(0,0,0,0.95);
          }
          .mp-modal-header-bar {
            padding: 16px 22px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: #141414;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            font-size: 1.15em;
          }
          .mp-modal-close {
            background: transparent;
            border: none;
            color: #aaa;
            font-size: 32px;
            cursor: pointer;
            line-height: 1;
            transition: color 0.2s ease;
          }
          .mp-modal-close:hover { color: #fff; }
          .mp-modal-body-content {
            padding: 22px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 22px;
          }
          .mp-detail-top {
            display: flex;
            gap: 22px;
            align-items: flex-start;
          }
          .mp-detail-poster {
            width: 210px;
            aspect-ratio: 2/3;
            object-fit: cover;
            border-radius: 12px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.7);
            flex-shrink: 0;
          }
          .mp-detail-meta {
            display: flex;
            flex-direction: column;
            gap: 14px;
            flex-grow: 1;
          }
          .mp-detail-title {
            font-size: 2em;
            font-weight: 800;
            line-height: 1.25;
            letter-spacing: -0.5px;
          }
          .mp-pills {
            display: flex;
            gap: 10px;
            align-items: center;
            flex-wrap: wrap;
          }
          .mp-pill {
            padding: 7px 14px;
            border-radius: 8px;
            font-size: 1em;
            font-weight: 700;
            display: inline-flex;
            align-items: center;
            gap: 6px;
          }
          .mp-meta-rows {
            display: flex;
            flex-direction: column;
            gap: 10px;
            background: rgba(255,255,255,0.04);
            padding: 16px 18px;
            border-radius: 12px;
            border: 1px solid rgba(255,255,255,0.08);
          }
          .mp-meta-row {
            font-size: 1.05em;
            line-height: 1.5;
            color: #eee;
          }
          .mp-meta-row strong {
            color: #bbb;
            margin-right: 6px;
            font-size: 1.05em;
          }
          .mp-section-heading {
            margin-bottom: 10px;
            font-size: 1.25em;
            font-weight: 700;
          }
          .mp-synopsis-box {
            background: rgba(255,255,255,0.04);
            padding: 18px;
            border-radius: 12px;
            border-left: 4px solid var(--primary-color, #03a9f4);
            line-height: 1.65;
            font-size: 1.05em;
            color: #eee;
          }
          .mp-video-container {
            position: relative;
            width: 100%;
            padding-bottom: 56.25%;
            height: 0;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 10px 25px rgba(0,0,0,0.8);
            border: 1px solid rgba(255, 255, 255, 0.1);
            background: #000;
          }
          .mp-video-container iframe {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            border: 0;
          }

          /* KOMPAKT LÁBLÉC GOMBOK */
          .mp-modal-footer {
            padding: 14px 20px;
            background: #141414;
            display: flex;
            gap: 10px;
            justify-content: flex-end;
            align-items: center;
            border-top: 1px solid rgba(255, 255, 255, 0.1);
          }
          .mp-btn {
            padding: 9px 14px;
            border-radius: 8px;
            font-weight: 600;
            text-decoration: none;
            cursor: pointer;
            border: none;
            font-size: 0.9em;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            transition: background 0.2s ease, transform 0.1s ease;
            box-sizing: border-box;
            white-space: nowrap;
          }
          .mp-btn-primary { background: #e50914; color: #fff; }
          .mp-btn-primary:hover { background: #b20710; }
          .mp-btn-secondary { background: rgba(255,255,255,0.15); color: #fff; }
          .mp-btn-secondary:hover { background: rgba(255,255,255,0.25); }

          /* MOBIL OPTIMALIZÁLÁS (600px alatt) */
          @media (max-width: 600px) {
            #mp-detail-overlay { padding: 8px; }
            .mp-modal-body-content { padding: 16px; gap: 16px; }
            .mp-detail-top { flex-direction: column; align-items: center; text-align: center; }
            .mp-detail-poster { width: 150px; }
            .mp-pills { justify-content: center; }
            .mp-detail-title { font-size: 1.5em; text-align: center; }
            .mp-meta-row { font-size: 1em; }
            .mp-synopsis-box { font-size: 1em; }

            .mp-modal-footer {
              padding: 10px 14px;
              justify-content: flex-end;
              gap: 8px;
            }
            .mp-btn {
              padding: 8px 12px;
              font-size: 1.1em;
            }
            .mp-btn .btn-text {
              display: none;
            }
          }
        </style>
        <div class="mp-modal-container">
          <div class="mp-modal-header-bar">
            <span style="font-weight:700; color:#ccc;">🎬 Film adatlap</span>
            <button id="mp-modal-close-btn" class="mp-modal-close" aria-label="Bezárás">&times;</button>
          </div>
          <div id="mp-modal-content-body" class="mp-modal-body-content"></div>
          <div id="mp-modal-footer-box" class="mp-modal-footer"></div>
        </div>
      `;
      document.body.appendChild(overlay);

      const closeBtn = overlay.querySelector('#mp-modal-close-btn');
      closeBtn.addEventListener('click', () => this.closeDetailModal());

      // Egy delegált click-figyelő: hátteret kattintva bezárja a modalt,
      // a lábléc "megnyitás" gombjait (data-open-url) pedig új fülön nyitja meg.
      // Delegáltként regisztráljuk, mert a lábléc/tartalom innerHTML-je minden
      // filmnél újragenerálódik, egy közvetlen onclick-attribútum törékenyebb
      // (idézőjelre érzékeny) lenne.
      overlay.addEventListener('click', (e) => {
        const openBtn = e.target.closest('[data-open-url]');
        if (openBtn) {
          window.open(openBtn.getAttribute('data-open-url'), '_blank');
          return;
        }
        if (e.target === overlay) this.closeDetailModal();
      });

      // Escape billentyűvel is bezárható a modal.
      document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !overlay.classList.contains('hidden')) {
          this.closeDetailModal();
        }
      });
    }
    return overlay;
  }

  openDetailModal(movie) {
    const overlay = this.createDetailModal();
    const bodyBox = overlay.querySelector('#mp-modal-content-body');
    const footerBox = overlay.querySelector('#mp-modal-footer-box');

    const { bg: platformBg, name: platformName } = this.getPlatformInfo(movie);

    const videoId = this.getYouTubeId(movie.trailer_url);
    const origin = encodeURIComponent(window.location.origin);
    const embedUrl = videoId
      ? `https://www.youtube-nocookie.com/embed/${videoId}?enablejsapi=1&origin=${origin}`
      : '';

    const title = this.escapeHtml(movie.title);
    const poster = this.escapeHtml(movie.poster);
    const date = this.escapeHtml(movie.date);
    const runtime = this.escapeHtml(movie.runtime) || 'Nincs adat';
    const genres = this.escapeHtml(movie.genres) || 'Nincs adat';
    const director = this.escapeHtml(movie.director) || 'Nincs adat';
    const cast = this.escapeHtml(movie.cast) || 'Nincs adat';
    const synopsis = movie.synopsis ? this.escapeHtml(movie.synopsis) : 'Ehhez a filmhez nincs részletes leírás.';

    bodyBox.innerHTML = `
      <div class="mp-detail-top">
        <img class="mp-detail-poster" src="${poster}" alt="${title}" />
        <div class="mp-detail-meta">
          <div class="mp-detail-title">${title}</div>
          <div class="mp-pills">
            ${movie.is_streaming ?
              `<span class="mp-pill" style="background:${platformBg}; color:#fff;">📺 ${this.escapeHtml(platformName)}</span>` :
              `<span class="mp-pill" style="background:#2e7d32; color:#fff;">🎬 Mozis Premier</span>`}
            <span class="mp-pill" style="background:rgba(255,255,255,0.1); color:#fff;">📅 ${date}</span>
          </div>
          <div class="mp-meta-rows">
            <div class="mp-meta-row"><strong>⏱️ Játékidő:</strong> ${runtime}</div>
            <div class="mp-meta-row"><strong>🎭 Műfaj:</strong> ${genres}</div>
            <div class="mp-meta-row"><strong>🎬 Rendező:</strong> ${director}</div>
            <div class="mp-meta-row"><strong>👥 Szereplők:</strong> ${cast}</div>
          </div>
        </div>
      </div>
      <div>
        <div class="mp-section-heading">📖 Tartalom</div>
        <div class="mp-synopsis-box">${synopsis}</div>
      </div>
      ${embedUrl ? `
        <div>
          <div class="mp-section-heading">🎬 Előzetes</div>
          <div class="mp-video-container">
            <iframe id="mp-trailer-iframe"
                    src="${embedUrl}"
                    title="YouTube video player"
                    frameborder="0"
                    referrerpolicy="strict-origin-when-cross-origin"
                    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                    allowfullscreen>
            </iframe>
          </div>
        </div>
      ` : ''}
    `;

    footerBox.innerHTML = `
      ${movie.trailer_url ? `
        <button class="mp-btn mp-btn-primary" data-open-url="${this.escapeHtml(movie.trailer_url)}" title="Megnyitás YouTube-on">
          <span class="btn-icon">▶️</span>
          <span class="btn-text">YouTube</span>
        </button>` : ''}
      <button class="mp-btn mp-btn-secondary" data-open-url="${this.escapeHtml(movie.detail_url)}" title="Megnyitás mozipremierek.hu-n">
        <span class="btn-icon">🔗</span>
        <span class="btn-text">mozipremierek.hu</span>
      </button>
    `;

    overlay.classList.remove('hidden');
  }

  closeDetailModal() {
    const overlay = document.getElementById('mp-detail-overlay');
    if (overlay) {
      const iframe = overlay.querySelector('#mp-trailer-iframe');
      if (iframe) iframe.src = "";
      overlay.classList.add('hidden');
    }
  }

  async loadMovies() {
    this.content.innerHTML = `<p class="mp-loading-text">Betöltés…</p>`;
    try {
      const res = await fetch('/local/mozipremierek.json?v=' + new Date().getTime());
      const rawData = await res.json();

      // Dátum szerinti növekvő sorbarendezés minden kategóriában
      this.sortedMoviesData = {
        cinema_current: this.sortMoviesByDate(rawData.cinema_current || []),
        streaming_current: this.sortMoviesByDate(rawData.streaming_current || []),
        cinema_past: this.sortMoviesByDate(rawData.cinema_past || [])
      };

      this.render(this.sortedMoviesData);
    } catch (e) {
      this.content.innerHTML = `<p style="padding: 16px; color: var(--error-color, red);">Nem sikerült betölteni az adatokat.</p>`;
    }
  }

  renderGrid(movies, category) {
    if (!movies || movies.length === 0) {
      return `<p style="color: var(--secondary-text-color, #aaa);">Nincs megjeleníthető premier ebben a kategóriában.</p>`;
    }

    return `
      <div class="movie-grid">
        ${movies.map((movie, index) => {
          const { bg: platformBg, name: platformName } = this.getPlatformInfo(movie);
          const title = this.escapeHtml(movie.title);
          const poster = this.escapeHtml(movie.poster);
          const date = this.escapeHtml(movie.date);

          return `
            <div class="movie-card" data-category="${category}" data-index="${index}"
                 role="button" tabindex="0" aria-label="${title} részletei">
              <div class="poster-container">
                ${movie.trailer_url ? `
                  <div class="clapper-badge" title="Előzetes elérhető">🎬</div>
                ` : ''}
                <img class="poster-img" src="${poster}" alt="${title}" loading="lazy" />
                ${movie.is_streaming ? `
                  <div class="platform-badge" style="background: ${platformBg};">${this.escapeHtml(platformName)}</div>
                ` : ''}
              </div>
              <div class="movie-info">
                <div class="movie-title">${title}</div>
                <div class="movie-date">📅 ${date}</div>
              </div>
            </div>
          `;
        }).join('')}
      </div>
    `;
  }

  render(data) {
    const cinemaHtml = this.renderGrid(data.cinema_current, 'cinema_current');
    const streamingHtml = this.renderGrid(data.streaming_current, 'streaming_current');
    const pastHtml = this.renderGrid(data.cinema_past, 'cinema_past');

    this.content.innerHTML = `
      <div>
        <div class="section-title">🎬 Mozis premierek (Ezen és jövő héten)</div>
        ${cinemaHtml}
      </div>
      <div>
        <div class="section-title">📺 Streaming premierek (Ezen és jövő héten)</div>
        ${streamingHtml}
      </div>
      <div>
        <div class="section-title">🍿 Még a mozikban (Elmúlt 3 hét)</div>
        ${pastHtml}
      </div>
    `;
  }

  getCardSize() {
    return 6;
  }
}

customElements.define('mozipremierek-card', MozipremierekCard);
