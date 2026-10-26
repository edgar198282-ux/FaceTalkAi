(function () {
  var root = document.documentElement;
  function resize() {
    root.style.setProperty('--abaj-screen-height', window.innerHeight + 'px');
    var touch = navigator.maxTouchPoints > 0 || 'ontouchstart' in window;
    root.classList.toggle('abajTouchScreen', touch && window.innerWidth >= 700);
  }
  resize();
  window.addEventListener('resize', resize);
  window.addEventListener('orientationchange', resize);
  if (window.visualViewport) window.visualViewport.addEventListener('resize', resize);
  if (!Promise.allSettled) {
    Promise.allSettled = function (values) {
      return Promise.all(Array.from(values).map(function (value) {
        return Promise.resolve(value).then(function (result) {
          return {status: 'fulfilled', value: result};
        }, function (reason) {
          return {status: 'rejected', reason: reason};
        });
      }));
    };
  }
})();
