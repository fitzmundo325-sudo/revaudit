(function () {
  'use strict';

  var overlay = null;
  var showTimer = null;
  var minVisibilityTimer = null;
  var isLoadingVisible = false;

  function getOverlay() {
    if (!overlay) {
      overlay = document.getElementById('spa-loading-overlay');
    }
    return overlay;
  }

  function showLoading() {
    var el = getOverlay();
    if (!el) return;
    el.classList.add('spa-visible');
    isLoadingVisible = true;
  }

  function hideLoading() {
    clearTimeout(showTimer);
    showTimer = null;
    
    // On initial load, respect the minimum visibility timer
    if (isInitialLoad) {
      return; // Don't hide until initial load timer expires
    }
    
    // Ensure overlay stays visible for at least 500ms during SPA navigation
    if (isLoadingVisible && !minVisibilityTimer) {
      minVisibilityTimer = setTimeout(function () {
        var el = getOverlay();
        if (el) {
          el.classList.remove('spa-visible');
        }
        isLoadingVisible = false;
        minVisibilityTimer = null;
      }, 500);
    } else if (!isLoadingVisible) {
      var el = getOverlay();
      if (el) {
        el.classList.remove('spa-visible');
      }
    }
  }

  // Track if this is initial page load
  var isInitialLoad = true;
  var initialLoadMinTimeout = null;

  window.hideSpaLoading = hideLoading;
  window.showSpaLoading = function () {
    clearTimeout(showTimer);
    showLoading();
  };

  // On initial load, keep overlay visible for minimum time (600ms), then hide it
  if (isInitialLoad) {
    initialLoadMinTimeout = setTimeout(function () {
      isInitialLoad = false;
      hideLoading();
    }, 600);
  }

  window.addEventListener('pageshow', hideLoading);
  window.addEventListener('load', hideLoading);

  document.addEventListener('click', function (e) {
    var anchor = e.target.closest('a[href]');
    if (!anchor) return;

    var href = anchor.getAttribute('href');
    if (!href || href === '#' || href.startsWith('#') || href.startsWith('javascript:')) return;
    if (anchor.target === '_blank') return;
    if (anchor.hasAttribute('download')) return;
    if (anchor.hasAttribute('data-no-spinner')) return;

    try {
      var url = new URL(href, window.location.origin);
      if (url.origin !== window.location.origin) return;
    } catch (err) {
      return;
    }

    clearTimeout(showTimer);
    showTimer = setTimeout(showLoading, 0);
  });

  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form || form.tagName !== 'FORM') return;
    if (e.defaultPrevented) return;
    if (form.getAttribute('data-no-spinner')) return;
    // Inline onsubmit handlers (e.g. `return confirm(...)`) may cancel the
    // submission; if so, no navigation happens and the overlay would stick.
    if (form.getAttribute('onsubmit')) return;
    clearTimeout(showTimer);
    showTimer = setTimeout(showLoading, 0);
  });

  if (typeof MutationObserver !== 'undefined') {
    var checkModalVisibility = function (node) {
      if (!node || node.nodeType !== 1) return;
      var id = (node.id || '').toLowerCase();
      var className = (typeof node.className === 'string' ? node.className : '').toLowerCase();
      if (id.indexOf('modal') !== -1 || className.indexOf('modal') !== -1 || node.hasAttribute('data-modal-content')) {
        if (!node.classList.contains('hidden') && node.style.display !== 'none') {
          hideLoading();
        }
      }
    };

    var observer = new MutationObserver(function (mutations) {
      for (var i = 0; i < mutations.length; i++) {
        var m = mutations[i];
        if (m.type === 'attributes') {
          checkModalVisibility(m.target);
        } else if (m.type === 'childList') {
          for (var j = 0; j < m.addedNodes.length; j++) {
            checkModalVisibility(m.addedNodes[j]);
          }
        }
      }
    });

    var startObserving = function () {
      if (document.body) {
        observer.observe(document.body, {
          attributes: true,
          attributeFilter: ['class', 'style', 'hidden'],
          subtree: true,
          childList: true
        });
      }
    };

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', startObserving);
    } else {
      startObserving();
    }
  }

})();