// 페이지별 인라인 스크립트에서 공통으로 쓸 만한 로직이 생기면 여기에 추가한다.

(function() {
  var toggle = document.getElementById('navToggle');
  var links = document.getElementById('navLinks');
  if (!toggle || !links) return;

  toggle.addEventListener('click', function() {
    var isOpen = links.classList.toggle('open');
    toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
  });

  // 메뉴 항목을 클릭해 페이지를 이동할 때는 메뉴가 열린 채로 남지 않게 닫아준다.
  links.querySelectorAll('a').forEach(function(a) {
    a.addEventListener('click', function() {
      links.classList.remove('open');
      toggle.setAttribute('aria-expanded', 'false');
    });
  });
})();
