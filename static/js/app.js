document.addEventListener('DOMContentLoaded', () => {
  const menuToggle = document.getElementById('menuToggle');
  const sidebar = document.getElementById('sidebar');
  if (menuToggle && sidebar) {
    menuToggle.addEventListener('click', () => sidebar.classList.toggle('sidebar-open'));
  }

  document.querySelectorAll('.flash-close').forEach(button => {
    button.addEventListener('click', () => button.closest('.flash-message').remove());
  });

  // Make external links and primary form interactions feel consistent.
  document.querySelectorAll('form').forEach(form => {
    form.addEventListener('submit', () => {
      const submit = form.querySelector('button[type="submit"]');
      if (submit && form.checkValidity()) {
        submit.dataset.originalText = submit.innerHTML;
        submit.disabled = true;
        submit.innerHTML = 'Saving…';
      }
    });
  });
});
