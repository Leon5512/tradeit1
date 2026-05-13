/**
 * TradeIt — animations.js
 * Положи файл в /static/animations.js
 * Подключи в base.html перед </body>:
 *   <script src="{{ url_for('static', filename='animations.js') }}" defer></script>
 */

(function () {
  'use strict';

  /* ── 1. Fade-in при скролле ── */
  function initScrollReveal() {
    // Применяем класс fade-in-up ко всем карточкам и секциям
    const selectors = [
      '.ad-card', '.card', '[class*="ad-item"]',
      '[class*="listing"]', '.product-card',
      'article', 'section > *',
      'h1', 'h2', '.hero', '.banner'
    ].join(', ');

    const elements = document.querySelectorAll(selectors);

    elements.forEach(function (el) {
      // Не трогаем элементы внутри nav/footer
      if (el.closest('nav, footer, header')) return;
      el.classList.add('fade-in-up');
    });

    const observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          observer.unobserve(entry.target); // однократно
        }
      });
    }, {
      threshold: 0.12,
      rootMargin: '0px 0px -40px 0px'
    });

    document.querySelectorAll('.fade-in-up').forEach(function (el) {
      observer.observe(el);
    });
  }

  /* ── 2. Page transition overlay ── */
  function initPageTransitions() {
    const overlay = document.createElement('div');
    overlay.className = 'page-transition-overlay';
    document.body.appendChild(overlay);

    // Анимация входа: overlay схлопывается при загрузке
    requestAnimationFrame(function () {
      overlay.classList.add('exit');
    });

    // Анимация выхода при клике на ссылки
    document.addEventListener('click', function (e) {
      const link = e.target.closest('a[href]');
      if (!link) return;

      const href = link.getAttribute('href');
      // Пропускаем якоря, mailto, внешние ссылки, target="_blank"
      if (!href ||
          href.startsWith('#') ||
          href.startsWith('mailto:') ||
          href.startsWith('tel:') ||
          link.target === '_blank' ||
          link.hostname !== location.hostname) return;

      e.preventDefault();
      overlay.style.animation = 'none';
      overlay.style.transform = 'scaleY(1)';
      overlay.style.transformOrigin = 'bottom';

      setTimeout(function () {
        window.location.href = href;
      }, 320);
    });
  }

  /* ── 3. Ripple на кнопках ── */
  function initRipple() {
    document.addEventListener('click', function (e) {
      const btn = e.target.closest('button, .btn, input[type="submit"], input[type="button"]');
      if (!btn) return;

      const rect = btn.getBoundingClientRect();
      const ripple = document.createElement('span');
      const size = Math.max(rect.width, rect.height);

      Object.assign(ripple.style, {
        position: 'absolute',
        width: size + 'px',
        height: size + 'px',
        left: (e.clientX - rect.left - size / 2) + 'px',
        top: (e.clientY - rect.top - size / 2) + 'px',
        background: 'rgba(255,255,255,0.35)',
        borderRadius: '50%',
        transform: 'scale(0)',
        animation: 'rippleAnim 0.55s ease-out forwards',
        pointerEvents: 'none',
        zIndex: '10'
      });

      // Кнопка должна быть relative
      const prev = btn.style.position;
      if (!prev || prev === 'static') btn.style.position = 'relative';
      btn.style.overflow = 'hidden';
      btn.appendChild(ripple);

      ripple.addEventListener('animationend', function () {
        ripple.remove();
      });
    });

    // Добавляем keyframe для ripple через stylesheet
    if (!document.getElementById('ripple-style')) {
      const style = document.createElement('style');
      style.id = 'ripple-style';
      style.textContent = '@keyframes rippleAnim { to { transform: scale(3); opacity: 0; } }';
      document.head.appendChild(style);
    }
  }

  /* ── 4. Hover-эффект на изображениях: overflow clip ── */
  function initImageClip() {
    const cards = document.querySelectorAll(
      '.ad-card, .card, [class*="ad-item"], .product-card'
    );
    cards.forEach(function (card) {
      const img = card.querySelector('img');
      if (!img) return;
      // Убеждаемся что родитель имеет overflow:hidden
      const wrapper = img.parentElement;
      wrapper.style.overflow = 'hidden';
    });
  }

  /* ── 5. Форма: встряска при ошибке ── */
  function initFormShake() {
    document.querySelectorAll('form').forEach(function (form) {
      form.addEventListener('submit', function () {
        // Сбрасываем анимацию прошлых ошибок
        form.querySelectorAll('.error, .invalid, [class*="error"]').forEach(function (el) {
          el.classList.remove('error-shake');
          void el.offsetWidth; // reflow
          el.classList.add('error-shake');
        });
      });
    });
  }

  /* ── 6. Счётчик непрочитанных: пульс-анимация ── */
  function initBadgePulse() {
    const badges = document.querySelectorAll(
      '.badge, [class*="unread"], [class*="count"], [class*="notify"]'
    );
    badges.forEach(function (badge) {
      if (parseInt(badge.textContent) > 0) {
        badge.style.animation = 'pulse 2s ease infinite';
      }
    });
  }

  /* ── Инициализация ── */
  function init() {
    initScrollReveal();
    initPageTransitions();
    initRipple();
    initImageClip();
    initFormShake();
    initBadgePulse();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
