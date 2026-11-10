/**
 * app.js — Logique de l'interface web CalorIA (JavaScript pur, sans bibliothèque externe).
 *
 * Ce script communique avec notre serveur Python `app.py` via `fetch(...)`
 * pour afficher les repas du jour, rechercher des produits et calculer les calories.
 */

// Repères caloriques définis pour CalorIA
const GOAL_MIN = 1650;
const GOAL_MAX = 1750;
const REF_KCAL = 1990;

// État courant de la page
let currentDate = getLocalTodayISO();
let localFoods = [];
let ciqualFoods = [];
let offFoods = [];
let selectedFood = null;

// Récupération des éléments HTML principaux
const datePicker = document.getElementById("date-picker");
const prevDayBtn = document.getElementById("prev-day");
const nextDayBtn = document.getElementById("next-day");
const todayBtn = document.getElementById("today-btn");

const dayTotalEl = document.getElementById("day-total-kcal");
const goalStatusEl = document.getElementById("goal-status");
const refRemainingEl = document.getElementById("ref-remaining");
const progressBarEl = document.getElementById("progress-bar");

const searchForm = document.getElementById("search-form");
const searchInput = document.getElementById("search-input");
const offSearchBtn = document.getElementById("off-search-btn");
const searchFeedback = document.getElementById("search-feedback");
const resultsContainer = document.getElementById("results-container");

const selectedBox = document.getElementById("selected-box");
const selectedNameEl = document.getElementById("selected-name");
const selectedBrandEl = document.getElementById("selected-brand");
const selectedKcalInfoEl = document.getElementById("selected-kcal-info");
const clearSelectedBtn = document.getElementById("clear-selected");

const addEntryForm = document.getElementById("add-entry-form");
const mealSelect = document.getElementById("meal-select");
const qtyInput = document.getElementById("qty-input");
const unitSelect = document.getElementById("unit-select");
const portionWeightRow = document.getElementById("portion-weight-row");
const customPortionGramsInput = document.getElementById("custom-portion-grams");
const calcPreviewEl = document.getElementById("calc-preview");

const manualDetails = document.getElementById("manual-details");
const manualFoodForm = document.getElementById("manual-food-form");
const mealsContainer = document.getElementById("meals-container");
const historyListEl = document.getElementById("history-list");

// ------------------------------------------------------------------
// Utilitaires de dates et formatage
// ------------------------------------------------------------------

/** Renvoie la date d'aujourd'hui au format YYYY-MM-DD (heure locale). */
function getLocalTodayISO() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** Ajoute ou retire `deltaDays` jours à une date YYYY-MM-DD. */
function shiftDate(isoDate, deltaDays) {
  const [y, m, d] = isoDate.split("-").map(Number);
  const dateObj = new Date(y, m - 1, d);
  dateObj.setDate(dateObj.getDate() + deltaDays);
  const ny = dateObj.getFullYear();
  const nm = String(dateObj.getMonth() + 1).padStart(2, "0");
  const nd = String(dateObj.getDate()).padStart(2, "0");
  return `${ny}-${nm}-${nd}`;
}

/** Formate un nombre de calories proprement (ex: 1 650). */
function formatKcal(val) {
  return Math.round(Number(val) || 0).toLocaleString("fr-FR");
}

/** Affiche un message d'info ou d'erreur sous la barre de recherche. */
function showFeedback(message, isError = false) {
  if (!message) {
    searchFeedback.classList.add("hidden");
    searchFeedback.textContent = "";
    searchFeedback.classList.remove("error");
    return;
  }
  searchFeedback.textContent = message;
  searchFeedback.classList.remove("hidden");
  searchFeedback.classList.toggle("error", isError);
}

// ------------------------------------------------------------------
// Chargement des données du jour et de l'historique
// ------------------------------------------------------------------

async function loadDay(dateStr) {
  currentDate = dateStr;
  datePicker.value = currentDate;

  const response = await fetch(`/api/day?date=${encodeURIComponent(currentDate)}`);
  const data = await response.json();

  renderSummary(data.total_kcal || 0);
  renderMeals(data.menus || []);
  loadHistory();
}

function renderSummary(totalKcal) {
  const rounded = Math.round(totalKcal);
  dayTotalEl.textContent = formatKcal(rounded);

  // Mise à jour du badge d'objectif (1 650 - 1 750 kcal)
  goalStatusEl.className = "badge";
  if (rounded < GOAL_MIN) {
    goalStatusEl.textContent = `Encore ${formatKcal(GOAL_MIN - rounded)} kcal pour atteindre l'objectif`;
  } else if (rounded <= GOAL_MAX) {
    goalStatusEl.textContent = "Dans l'objectif quotidien !";
    goalStatusEl.classList.add("in-goal");
  } else if (rounded <= REF_KCAL) {
    goalStatusEl.textContent = "Au-dessus de l'objectif, sous le repère de 1 990 kcal";
    goalStatusEl.classList.add("above-goal");
  } else {
    goalStatusEl.textContent = "Repère de 1 990 kcal dépassé";
    goalStatusEl.classList.add("above-ref");
  }

  // Écart par rapport au repère d'activité modérée (1 990 kcal)
  const diffRef = REF_KCAL - rounded;
  if (diffRef >= 0) {
    refRemainingEl.textContent = `Reste ${formatKcal(diffRef)} kcal par rapport au repère`;
  } else {
    refRemainingEl.textContent = `Dépassé de ${formatKcal(Math.abs(diffRef))} kcal`;
  }

  // Largeur de la barre de progression sur l'échelle 0 -> 1 990 kcal
  const pct = Math.min(100, Math.max(0, (rounded / REF_KCAL) * 100));
  progressBarEl.style.width = `${pct.toFixed(1)}%`;
}

function renderMeals(menus) {
  mealsContainer.innerHTML = "";

  for (const menu of menus) {
    const card = document.createElement("div");
    card.className = "meal-card";

    // En-tête du menu (nom + total kcal + bouton + rapide)
    const header = document.createElement("div");
    header.className = "meal-header";

    const title = document.createElement("span");
    title.className = "meal-title";
    title.textContent = menu.name;

    const right = document.createElement("div");
    right.className = "meal-right";

    const totalSpan = document.createElement("span");
    totalSpan.className = "meal-total";
    totalSpan.textContent = `${formatKcal(menu.total_kcal)} kcal`;

    const quickAddBtn = document.createElement("button");
    quickAddBtn.type = "button";
    quickAddBtn.className = "btn btn-secondary";
    quickAddBtn.textContent = "+";
    quickAddBtn.title = `Ajouter dans ${menu.name}`;
    quickAddBtn.addEventListener("click", () => {
      mealSelect.value = menu.name;
      searchInput.focus();
    });

    right.appendChild(totalSpan);
    right.appendChild(quickAddBtn);
    header.appendChild(title);
    header.appendChild(right);
    card.appendChild(header);

    // Liste des aliments dans ce menu
    if (!menu.entries || menu.entries.length === 0) {
      const empty = document.createElement("div");
      empty.className = "empty-msg";
      empty.textContent = "Aucun aliment enregistré.";
      card.appendChild(empty);
    } else {
      const ul = document.createElement("ul");
      ul.className = "entry-list";

      for (const entry of menu.entries) {
        const li = document.createElement("li");
        li.className = "entry-item";

        const leftInfo = document.createElement("div");
        const nameEl = document.createElement("div");
        nameEl.textContent = entry.food_brand
          ? `${entry.food_name} (${entry.food_brand})`
          : entry.food_name;

        const qtyEl = document.createElement("div");
        qtyEl.className = "entry-qty";
        if (entry.unit === "portion") {
          qtyEl.textContent = `${entry.quantity} portion(s) · ${entry.grams_equivalent} g`;
        } else {
          qtyEl.textContent = `${entry.quantity} g`;
        }

        leftInfo.appendChild(nameEl);
        leftInfo.appendChild(qtyEl);

        const actions = document.createElement("div");
        actions.className = "entry-actions";

        const kcalEl = document.createElement("strong");
        kcalEl.textContent = `${formatKcal(entry.kcal_calculated)} kcal`;

        const delBtn = document.createElement("button");
        delBtn.type = "button";
        delBtn.className = "btn-delete";
        delBtn.title = "Supprimer cette ligne";
        delBtn.textContent = "×";
        delBtn.addEventListener("click", () => deleteEntry(entry.id));

        actions.appendChild(kcalEl);
        actions.appendChild(delBtn);

        li.appendChild(leftInfo);
        li.appendChild(actions);
        ul.appendChild(li);
      }

      card.appendChild(ul);
    }

    mealsContainer.appendChild(card);
  }
}

async function deleteEntry(entryId) {
  const response = await fetch(`/api/entries/${entryId}`, { method: "DELETE" });
  if (response.ok) {
    loadDay(currentDate);
  }
}

async function loadHistory() {
  const response = await fetch("/api/history");
  const data = await response.json();
  const days = data.days || [];

  historyListEl.innerHTML = "";
  if (days.length === 0) {
    const empty = document.createElement("span");
    empty.className = "empty-msg";
    empty.textContent = "Aucune journée enregistrée pour le moment.";
    historyListEl.appendChild(empty);
    return;
  }

  for (const day of days) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "history-chip";
    if (day.entry_date === currentDate) {
      btn.classList.add("active");
    }
    btn.textContent = `${day.entry_date} · ${formatKcal(day.total_kcal)} kcal`;
    btn.addEventListener("click", () => loadDay(day.entry_date));
    historyListEl.appendChild(btn);
  }
}

// ------------------------------------------------------------------
// Recherche locale + Open Food Facts + sélection de produit
// ------------------------------------------------------------------

async function loadLocalFoods(query = "") {
  const response = await fetch(`/api/foods?q=${encodeURIComponent(query)}`);
  const data = await response.json();
  localFoods = data.foods || [];
  ciqualFoods = data.ciqual || [];
  renderSearchResults();
}

async function searchOpenFoodFacts(query) {
  const q = query.trim();
  if (!q) {
    showFeedback("Tapez d'abord le nom d'un produit à chercher sur Open Food Facts.", true);
    return;
  }

  offSearchBtn.disabled = true;
  offSearchBtn.textContent = "Recherche...";
  showFeedback("Recherche sur Open Food Facts en cours...");

  try {
    const response = await fetch(`/api/openfoodfacts?q=${encodeURIComponent(q)}`);
    const data = await response.json();

    if (data.error) {
      offFoods = [];
      showFeedback(data.error, true);
    } else {
      offFoods = data.results || [];
      if (offFoods.length === 0) {
        showFeedback("Aucun produit avec valeur calorique trouvé sur Open Food Facts pour cette recherche.");
      } else {
        showFeedback(`${offFoods.length} produit(s) trouvé(s) sur Open Food Facts. Cliquez pour sélectionner.`);
      }
    }
  } catch (err) {
    offFoods = [];
    showFeedback("Impossible de contacter le serveur local.", true);
  } finally {
    offSearchBtn.disabled = false;
    offSearchBtn.textContent = "Open Food Facts";
    renderSearchResults();
  }
}

function renderSearchResults() {
  resultsContainer.innerHTML = "";

  if (localFoods.length > 0) {
    appendResultGroup("Mes aliments enregistrés", localFoods);
  }
  if (ciqualFoods.length > 0) {
    appendResultGroup("Table Ciqual (ANSES · hors ligne)", ciqualFoods);
  }
  if (offFoods.length > 0) {
    appendResultGroup("Open Food Facts (en ligne)", offFoods);
  }
}

function appendResultGroup(groupTitle, items) {
  const titleEl = document.createElement("div");
  titleEl.className = "result-group-title";
  titleEl.textContent = groupTitle;
  resultsContainer.appendChild(titleEl);

  for (const item of items) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "result-item";

    const left = document.createElement("div");
    const name = document.createElement("div");
    name.className = "result-name";
    name.textContent = item.name;

    const meta = document.createElement("div");
    meta.className = "result-meta";
    const details = [];
    if (item.brand) details.push(item.brand);
    if (item.portion_grams) {
      const pName = item.portion_name || "portion";
      details.push(`${pName} = ${item.portion_grams} g`);
    }
    meta.textContent = details.join(" · ");

    left.appendChild(name);
    if (meta.textContent) left.appendChild(meta);

    const kcal = document.createElement("div");
    kcal.className = "result-kcal";
    kcal.textContent = `${item.kcal_per_100g} kcal/100g`;

    btn.appendChild(left);
    btn.appendChild(kcal);
    btn.addEventListener("click", () => selectFood(item));
    resultsContainer.appendChild(btn);
  }
}

function selectFood(food) {
  selectedFood = food;
  selectedNameEl.textContent = food.name;
  selectedBrandEl.textContent = food.brand ? ` (${food.brand})` : "";

  let info = `${food.kcal_per_100g} kcal pour 100 g`;
  if (food.portion_grams) {
    info += ` · 1 ${food.portion_name || "portion"} = ${food.portion_grams} g`;
  }
  selectedKcalInfoEl.textContent = info;

  // Par défaut : si le produit a un poids de portion connu, on garde l'unité choisie ou grammes
  customPortionGramsInput.value = food.portion_grams ? String(food.portion_grams) : "";
  if (unitSelect.value === "portion") {
    qtyInput.value = "1";
  } else {
    qtyInput.value = "100";
  }

  selectedBox.classList.remove("hidden");
  updatePreview();
}

function clearSelection() {
  selectedFood = null;
  selectedBox.classList.add("hidden");
}

function updatePreview() {
  if (!selectedFood) return;

  const qty = parseFloat(qtyInput.value) || 0;
  const unit = unitSelect.value;

  // Affiche le champ de poids de portion uniquement si l'unité est "portion" et que le poids manque
  const knownPortion = selectedFood.portion_grams ? Number(selectedFood.portion_grams) : null;
  if (unit === "portion" && !knownPortion) {
    portionWeightRow.classList.remove("hidden");
  } else {
    portionWeightRow.classList.add("hidden");
  }

  let grams = 0;
  if (unit === "g") {
    grams = qty;
  } else {
    const customPortion = parseFloat(customPortionGramsInput.value) || 0;
    const pGrams = knownPortion || customPortion;
    grams = qty * pGrams;
  }

  if (grams > 0) {
    const kcal = (grams / 100) * Number(selectedFood.kcal_per_100g);
    calcPreviewEl.textContent = `Aperçu : ${Math.round(grams * 10) / 10} g → ${formatKcal(kcal)} kcal`;
  } else {
    calcPreviewEl.textContent = "Aperçu : 0 kcal";
  }
}

// ------------------------------------------------------------------
// Événements utilisateur
// ------------------------------------------------------------------

datePicker.addEventListener("change", () => {
  if (datePicker.value) loadDay(datePicker.value);
});
prevDayBtn.addEventListener("click", () => loadDay(shiftDate(currentDate, -1)));
nextDayBtn.addEventListener("click", () => loadDay(shiftDate(currentDate, 1)));
todayBtn.addEventListener("click", () => loadDay(getLocalTodayISO()));

// Filtrer les aliments locaux en direct pendant la frappe
searchInput.addEventListener("input", () => {
  offFoods = [];
  showFeedback("");
  loadLocalFoods(searchInput.value);
});

// Cliquer sur "Open Food Facts" (ou appuyer sur Entrée dans la barre)
searchForm.addEventListener("submit", (e) => {
  e.preventDefault();
  searchOpenFoodFacts(searchInput.value);
});

clearSelectedBtn.addEventListener("click", clearSelection);

unitSelect.addEventListener("change", () => {
  qtyInput.value = unitSelect.value === "portion" ? "1" : "100";
  updatePreview();
});
qtyInput.addEventListener("input", updatePreview);
customPortionGramsInput.addEventListener("input", updatePreview);

// Ajouter le produit sélectionné au menu choisi
addEntryForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!selectedFood) return;

  const unit = unitSelect.value;
  const payload = {
    entry_date: currentDate,
    meal_type: mealSelect.value,
    quantity: parseFloat(qtyInput.value),
    unit: unit,
  };

  if (selectedFood.id) {
    payload.food_id = selectedFood.id;
  } else {
    payload.food = selectedFood;
  }

  if (unit === "portion" && !selectedFood.portion_grams) {
    const customPg = parseFloat(customPortionGramsInput.value);
    if (!customPg || customPg <= 0) {
      showFeedback("Indiquez le poids d'1 portion en grammes (ex: 30).", true);
      return;
    }
    payload.custom_portion_grams = customPg;
  }

  const response = await fetch("/api/entries", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();

  if (!response.ok) {
    showFeedback(data.error || "Erreur lors de l'ajout.", true);
    return;
  }

  showFeedback("Aliment ajouté au menu !");
  clearSelection();
  loadDay(currentDate);
  loadLocalFoods(searchInput.value);
});

// Enregistrer un aliment manuellement
manualFoodForm.addEventListener("submit", async (e) => {
  e.preventDefault();

  const payload = {
    name: document.getElementById("manual-name").value.trim(),
    brand: document.getElementById("manual-brand").value.trim(),
    kcal_per_100g: parseFloat(document.getElementById("manual-kcal").value),
    portion_name: document.getElementById("manual-portion-name").value.trim(),
    portion_grams: document.getElementById("manual-portion-grams").value || null,
  };

  const response = await fetch("/api/foods", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();

  if (!response.ok) {
    showFeedback(data.error || "Erreur lors de la création de l'aliment.", true);
    return;
  }

  manualFoodForm.reset();
  manualDetails.open = false;
  showFeedback(`"${data.food.name}" enregistré dans votre catalogue local.`);
  await loadLocalFoods(searchInput.value);
  selectFood(data.food);
});

// Initialisation au chargement de la page
loadDay(currentDate);
loadLocalFoods("");
