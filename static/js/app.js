// Progressive enhancement only: every form also works with JavaScript turned off.
// This file just avoids full page reloads when adding to the cart and placing an order.

(() => {
  const toast = document.querySelector("[data-toast]");
  let toastTimer;

  function showToast(message) {
    if (!toast) return;
    toast.textContent = message;
    toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toast.hidden = true; }, 2600);
  }

  function setCartCount(count) {
    document.querySelectorAll("[data-cart-count]").forEach((badge) => {
      badge.textContent = count;
      badge.dataset.empty = String(count === 0);
    });
  }

  // POST a form with fetch. On failure, throws an Error whose .fields holds any
  // per-field messages the server sent ({field_name: message}).
  async function postForm(form) {
    let response;
    try {
      response = await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        headers: { Accept: "application/json" },
      });
    } catch {
      throw new Error("Couldn't reach the server. Check that it's running and try again.");
    }
    let data = {};
    try {
      data = await response.json();
    } catch {
      // Non-JSON response (e.g. a server error page); handled below.
    }
    if (!response.ok) {
      const error = new Error(data.error || "Something went wrong on the server. Try again.");
      error.fields = data.fields || {};
      throw error;
    }
    return data;
  }

  // Menu page: "Add to cart"
  document.querySelectorAll("form[data-add-to-cart]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = form.querySelector("button");
      button.disabled = true;
      try {
        const data = await postForm(form);
        setCartCount(data.cart_count);
        showToast(`Added ${data.name} to your cart.`);
      } catch (error) {
        showToast(error.message);
      } finally {
        button.disabled = false;
      }
    });
  });

  // Checkout page: "Place order"
  const checkoutForm = document.querySelector("form[data-place-order]");
  if (checkoutForm) {
    const errorBox = checkoutForm.querySelector("[data-form-error]");

    const button = checkoutForm.querySelector("button[type=submit]");
    const idleLabel = button ? button.textContent.trim() : "Place order";
    const resultBox = checkoutForm.querySelector("[data-order-result]");

    // After ordering, keep the checkout on screen: lock the fields and show the
    // receipt right under the button so the address can be checked in place.
    function showOrderResult(data) {
      if (!resultBox || !data.html) {
        window.location.assign(data.redirect_url);
        return;
      }
      checkoutForm.querySelectorAll("input, select, textarea, button").forEach((field) => {
        field.disabled = true;
      });
      checkoutForm.classList.add("checkout-form--locked");
      button.textContent = "Order placed";
      resultBox.innerHTML = data.html;
      resultBox.hidden = false;
      resultBox.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    // The summary shows the exact values the server will receive. It is built
    // from the same FormData the POST uses, not from the visible inputs.
    const sentList = document.querySelector("[data-sent-list]");
    const sentFields = [
      ["full_name", "Name"],
      ["phone", "Phone"],
      ["street", "Street"],
      ["unit", "Apt/suite"],
      ["postal_code", "ZIP"],
      ["notes", "Courier note"],
    ];

    function renderSentDetails() {
      if (!sentList) return;
      const data = new FormData(checkoutForm);
      sentList.replaceChildren();
      sentFields.forEach(([name, label]) => {
        const value = String(data.get(name) || "").trim();
        if (!value) return;
        const dt = document.createElement("dt");
        dt.textContent = label;
        const dd = document.createElement("dd");
        dd.textContent = value;
        sentList.append(dt, dd);
      });
    }

    renderSentDetails();
    checkoutForm.addEventListener("input", renderSentDetails);
    checkoutForm.addEventListener("change", renderSentDetails);

    // Show (or clear) the message under each field; returns the first invalid field.
    function showFieldErrors(fields) {
      let firstInvalid = null;
      checkoutForm.querySelectorAll("[data-error-for]").forEach((line) => {
        const name = line.dataset.errorFor;
        const field = checkoutForm.elements[name];
        const message = fields[name] || "";
        line.textContent = message;
        line.hidden = !message;
        if (message) {
          field.setAttribute("aria-invalid", "true");
          firstInvalid = firstInvalid || field;
        } else {
          field.removeAttribute("aria-invalid");
        }
      });
      return firstInvalid;
    }

    // Once a flagged field is edited, drop its error instead of waiting for the next submit.
    checkoutForm.addEventListener("input", (event) => {
      const line = checkoutForm.querySelector(`[data-error-for="${event.target.name}"]`);
      if (line && !line.hidden) {
        line.hidden = true;
        event.target.removeAttribute("aria-invalid");
      }
      // Nothing left highlighted: the summary message no longer applies either.
      if (!checkoutForm.querySelector("[data-error-for]:not([hidden])")) {
        errorBox.hidden = true;
      }
    });

    checkoutForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      errorBox.hidden = true;
      showFieldErrors({});
      button.disabled = true;
      button.textContent = "Placing order…";
      try {
        const data = await postForm(checkoutForm);
        showOrderResult(data);
      } catch (error) {
        const firstInvalid = showFieldErrors(error.fields || {});
        errorBox.textContent = error.message;
        errorBox.hidden = false;
        button.disabled = false;
        button.textContent = idleLabel;
        if (firstInvalid) firstInvalid.focus();
      }
    });
  }
})();
