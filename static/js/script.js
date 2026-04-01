/**
 * script.js — SmartPark Cloud Parking System
 * Global JavaScript utilities
 */

// ── Navbar scroll effect ─────────────────────────────────────
window.addEventListener('scroll', () => {
  const nav = document.getElementById('navbar');
  if (nav) {
    nav.classList.toggle('scrolled', window.scrollY > 20);
  }
});

// ── Mobile nav toggle ────────────────────────────────────────
const navToggle = document.getElementById('navToggle');
const navLinks  = document.getElementById('navLinks');
if (navToggle && navLinks) {
  navToggle.addEventListener('click', () => {
    navLinks.classList.toggle('open');
    const icon = navToggle.querySelector('i');
    icon.className = navLinks.classList.contains('open')
      ? 'fas fa-times' : 'fas fa-bars';
  });
  // Close on outside click
  document.addEventListener('click', (e) => {
    if (!navToggle.contains(e.target) && !navLinks.contains(e.target)) {
      navLinks.classList.remove('open');
      const icon = navToggle.querySelector('i');
      if (icon) icon.className = 'fas fa-bars';
    }
  });
}

// ── Auto-dismiss flash messages ──────────────────────────────
document.querySelectorAll('.flash').forEach(flash => {
  setTimeout(() => {
    flash.style.opacity = '0';
    flash.style.transform = 'translateX(20px)';
    flash.style.transition = 'all .4s';
    setTimeout(() => flash.remove(), 400);
  }, 4500);
});

// ── Password toggle utility ──────────────────────────────────
function togglePwd(inputId, iconId) {
  const input = document.getElementById(inputId);
  const icon  = document.getElementById(iconId);
  if (!input) return;
  if (input.type === 'password') {
    input.type = 'text';
    if (icon) icon.className = 'fas fa-eye-slash';
  } else {
    input.type = 'password';
    if (icon) icon.className = 'fas fa-eye';
  }
}

// ── Vehicle number auto-uppercase ───────────────────────────
document.querySelectorAll('input[name="vehicle_no"]').forEach(el => {
  el.addEventListener('input', function () {
    this.value = this.value.toUpperCase();
  });
});

// ── Slot card hover pulse (slots page) ──────────────────────
document.querySelectorAll('.pv-slot').forEach((slot, i) => {
  slot.style.animationDelay = `${i * 0.08}s`;
  slot.style.animation = 'fadeInUp .4s ease both';
});

// ── Animate stat numbers on page load ───────────────────────
function animateCounter(el, target, duration = 1200) {
  let start = 0;
  const step = Math.ceil(target / (duration / 16));
  const timer = setInterval(() => {
    start += step;
    if (start >= target) {
      el.textContent = target;
      clearInterval(timer);
    } else {
      el.textContent = start;
    }
  }, 16);
}

document.querySelectorAll('.hstat-num, .sc-num, .as-num').forEach(el => {
  const val = parseInt(el.textContent.replace(/[^0-9]/g, ''), 10);
  if (!isNaN(val) && val > 0) {
    el.textContent = '0';
    // Use IntersectionObserver for on-scroll trigger
    const obs = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          animateCounter(el, val);
          obs.disconnect();
        }
      });
    }, { threshold: .3 });
    obs.observe(el);
  }
});

// ── Slot filter — live search on slots page ──────────────────
const slotSearch = document.getElementById('slotSearch');
if (slotSearch) {
  slotSearch.addEventListener('input', function () {
    const q = this.value.toLowerCase();
    document.querySelectorAll('.slot-card').forEach(card => {
      const text = card.textContent.toLowerCase();
      card.style.display = text.includes(q) ? '' : 'none';
    });
  });
}

// ── Booking form: set minimum date to today ──────────────────
const dateInput = document.getElementById('bookingDate');
if (dateInput && !dateInput.min) {
  const today = new Date().toISOString().split('T')[0];
  dateInput.min = today;
  dateInput.value = today;
}

// ── Confirm dialog for danger actions ───────────────────────
document.querySelectorAll('[data-confirm]').forEach(el => {
  el.addEventListener('click', function (e) {
    if (!confirm(this.dataset.confirm)) e.preventDefault();
  });
});

// ── Admin sidebar active highlight ──────────────────────────
const currentPath = window.location.pathname;
document.querySelectorAll('.sn-item').forEach(item => {
  if (item.getAttribute('href') === currentPath) {
    item.classList.add('active');
  }
});

// ── Table row click → view detail (booking history) ─────────
document.querySelectorAll('.data-table tbody tr[data-href]').forEach(row => {
  row.style.cursor = 'pointer';
  row.addEventListener('click', function (e) {
    if (!e.target.closest('button, a, form')) {
      window.location.href = this.dataset.href;
    }
  });
});

// ── Smooth scroll for anchor links ──────────────────────────
document.querySelectorAll('a[href^="#"]').forEach(a => {
  a.addEventListener('click', function (e) {
    const target = document.querySelector(this.getAttribute('href'));
    if (target) {
      e.preventDefault();
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });
});

// ── Print booking ticket ─────────────────────────────────────
function printTicket() {
  window.print();
}

// ── Toast notification utility ───────────────────────────────
function showToast(message, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `flash flash-${type}`;
  toast.innerHTML = `<i class="fas fa-info-circle"></i> ${message}
    <button class="flash-close" onclick="this.parentElement.remove()">×</button>`;
  let container = document.querySelector('.flash-container');
  if (!container) {
    container = document.createElement('div');
    container.className = 'flash-container';
    document.body.appendChild(container);
  }
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity .4s';
    setTimeout(() => toast.remove(), 400);
  }, 4000);
}
