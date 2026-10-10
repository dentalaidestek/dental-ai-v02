(() => {
  const form = document.querySelector('[data-expert-profile-form]');
  if (!form) return;
  const errorBox = form.querySelector('[data-expert-profile-error]');
  const submit = form.querySelector('[type="submit"]');
  const orcid = form.querySelector('[name="orcid_url"]');
  let sending = false;
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (sending) return;
    sending = true;
    errorBox.hidden = true;
    orcid?.removeAttribute('aria-invalid');
    // Capture the file and all form values before disabling the submit button.
    const body = new FormData(form);
    submit.disabled = true;
    form.setAttribute('aria-busy', 'true');
    try {
      const response = await fetch(form.action, {
        method: 'POST', body, credentials: 'same-origin', cache: 'no-store'
      });
      if (!response.ok) {
        const page = new DOMParser().parseFromString(await response.text(), 'text/html');
        const message = response.status < 500
          ? page.body.textContent.trim().slice(0, 600)
          : '';
        throw new Error(message || 'Profil kaydedilemedi. Bilgileriniz bu ekranda duruyor; tekrar deneyin.');
      }
      const target = new URL(response.url, location.href);
      if (target.origin !== location.origin || target.pathname === '/login') {
        throw new Error('Oturumunuz sona erdi. Bilgilerinizi kaybetmemek için başka bir sekmede giriş yapıp tekrar deneyin.');
      }
      if (!response.redirected || !target.searchParams.has('saved')) {
        throw new Error('Kaydetme sonucu doğrulanamadı. Bilgileriniz bu ekranda duruyor; tekrar deneyin.');
      }
      location.assign(target.href);
    } catch (error) {
      errorBox.textContent = error.message || 'Bağlantı kurulamadı. Tekrar deneyin.';
      errorBox.hidden = false;
      if (/ORCID/i.test(errorBox.textContent)) orcid?.setAttribute('aria-invalid', 'true');
      errorBox.focus();
      sending = false;
      submit.disabled = false;
      form.removeAttribute('aria-busy');
    }
  });
  window.addEventListener('pageshow', () => {
    sending = false;
    submit.disabled = false;
    form.removeAttribute('aria-busy');
  });
})();
