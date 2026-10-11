'use strict';
(function () {
  const root = document.getElementById('cases-dashboard');
  if (!root) return;
  const get = (id) => root.querySelector('#' + id);
  const normalize = (value) => value.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('pt-BR');
  const cards = Array.from(root.querySelectorAll('[data-case]'));
  const peers = Array.from(root.querySelectorAll('[data-peer]'));
  const filters = Array.from(root.querySelectorAll('[data-cases-filtro]'));
  // Ordinais vêm do Python; o navegador apenas permuta os elementos recebidos.
  function order(items, parent, key) {
    items.slice().sort((a, b) => {
      const left = a.getAttribute('data-ord-' + key);
      const right = b.getAttribute('data-ord-' + key);
      return left === right ? 0 : left < right ? -1 : 1;
    }).forEach((item) => parent.appendChild(item));
  }
  function filterCases() {
    const query = normalize(get('cases-busca').value);
    cards.forEach((card) => {
      card.hidden = !card.dataset.busca.includes(query) || filters.some((select) =>
        select.value && card.getAttribute('data-' + select.dataset.casesFiltro) !== select.value);
    });
    get('cases-sem-resultados').hidden = cards.some((card) => !card.hidden);
    get('cases-filtro-estado').textContent = 'Filtros aplicados ao catálogo; os indicadores acima conservam o recorte completo.';
  }
  function filterPeers() {
    const option = get('cases-referencia').selectedOptions[0];
    if (!option) return;
    const scope = get('cases-grupo').value;
    const ids = new Set((option.getAttribute('data-' + scope) || '').split(',').filter(Boolean));
    const query = normalize(get('cases-peer-busca').value);
    peers.forEach((row) => { row.hidden = !ids.has(row.dataset.peer) || !row.dataset.busca.includes(query); });
    get('cases-criterio').textContent = option.dataset.criterio + ' Grupo: ' +
      (scope === 'local' ? 'mesmo país.' : 'América Latina.') + ' Referência: ' + option.textContent.trim() + '.';
    get('cases-peer-limite').textContent = option.dataset.limite + ' Cada linha conserva seus cortes; retornos e preços não foram atualizados por esta seleção.';
    get('cases-peers-vazios').hidden = peers.some((row) => !row.hidden);
    order(peers, get('cases-peer-linhas'), get('cases-peer-ordem').value);
  }
  get('cases-busca').addEventListener('input', filterCases);
  filters.forEach((select) => select.addEventListener('change', filterCases));
  get('cases-ordem').addEventListener('change', () => order(cards, get('cases-lista'), get('cases-ordem').value));
  ['cases-referencia', 'cases-grupo', 'cases-peer-ordem'].forEach((id) => get(id).addEventListener('change', filterPeers));
  get('cases-peer-busca').addEventListener('input', filterPeers);
  root.querySelectorAll('[data-comparar]').forEach((button) => button.addEventListener('click', () => {
    get('cases-referencia').value = button.dataset.comparar;
    get('cases-peer-busca').value = '';
    filterPeers();
    const title = get('cases-comparaveis-titulo');
    title.focus();
    title.scrollIntoView({behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start'});
  }));
  const requested = new URLSearchParams(window.location.search).get('ativo');
  if (requested && Array.from(get('cases-referencia').options).some((option) => option.value === requested)) {
    get('cases-referencia').value = requested;
  }
  filterPeers();
}());
