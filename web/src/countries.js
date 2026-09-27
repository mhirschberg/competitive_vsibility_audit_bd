const codes = `AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW`.split(" ");
const displayNames = new Intl.DisplayNames(["en"], { type: "region" });
const preferredCodes = ["US", "GB", "DE", "FR", "NL", "CH", "AT", "CA", "AU"];
const aliases = { GB: "uk britain great britain england", US: "usa america", CZ: "czech republic", KR: "south korea", KP: "north korea", AE: "uae", NL: "holland" };

export const countries = codes.map((code) => ({ code, name: displayNames.of(code) }))
  .sort((a, b) => a.name.localeCompare(b.name, "en"));
const byCode = new Map(countries.map((country) => [country.code, country]));

function normalize(value) {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
}

export function findCountries(query) {
  const needle = normalize(query);
  if (needle) {
    const rank = ({ code, name }) => {
      const normalizedName = normalize(name);
      const normalizedAlias = normalize(aliases[code] || "");
      if (code.toLowerCase() === needle) return 0;
      if (normalizedAlias.split(" ").includes(needle)) return 1;
      if (normalizedName === needle) return 2;
      if (normalizedName.startsWith(needle)) return 3;
      if (normalizedName.includes(needle)) return 4;
      if (normalizedAlias.includes(needle)) return 5;
      return 6;
    };
    return countries.filter((country) => rank(country) < 6)
      .sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name, "en"));
  }
  const preferred = preferredCodes.map((code) => byCode.get(code));
  return [...preferred, ...countries.filter(({ code }) => !preferredCodes.includes(code))];
}

export function initCountryPicker(root) {
  const search = root.querySelector("#country-search");
  const hidden = root.querySelector("#country-code");
  const toggle = root.querySelector("#country-toggle");
  const list = root.querySelector("#country-options");
  let visible = [];
  let activeIndex = -1;
  let lastCode = hidden.value;

  function close() {
    list.hidden = true;
    search.setAttribute("aria-expanded", "false");
    toggle.setAttribute("aria-expanded", "false");
    search.removeAttribute("aria-activedescendant");
  }

  function highlight(index) {
    activeIndex = index;
    for (const [position, option] of [...list.querySelectorAll("[role=option]")].entries()) {
      option.classList.toggle("is-active", position === index);
    }
    if (index >= 0) {
      const option = list.querySelectorAll("[role=option]")[index];
      search.setAttribute("aria-activedescendant", option.id);
      option.scrollIntoView({ block: "nearest" });
    } else {
      search.removeAttribute("aria-activedescendant");
    }
  }

  function open(query = "") {
    if (search.disabled) return;
    visible = findCountries(query);
    list.replaceChildren();
    if (!visible.length) {
      const empty = document.createElement("p");
      empty.className = "country-empty";
      empty.textContent = "No matching countries";
      list.append(empty);
    } else {
      for (const country of visible) {
        const option = document.createElement("button");
        option.type = "button";
        option.id = `country-option-${country.code}`;
        option.className = "country-option";
        option.setAttribute("role", "option");
        option.setAttribute("aria-selected", country.code === hidden.value ? "true" : "false");
        option.tabIndex = -1;
        const name = document.createElement("span");
        name.textContent = country.name;
        const code = document.createElement("span");
        code.className = "country-option-code";
        code.textContent = country.code;
        option.append(name, code);
        option.addEventListener("click", () => selectCode(country.code));
        list.append(option);
      }
    }
    list.hidden = false;
    search.setAttribute("aria-expanded", "true");
    toggle.setAttribute("aria-expanded", "true");
    highlight(visible.findIndex(({ code }) => code === hidden.value));
  }

  function selectCode(code, focus = true) {
    const country = byCode.get(String(code).toUpperCase());
    if (!country) return false;
    hidden.value = country.code;
    lastCode = country.code;
    search.value = `${country.name} (${country.code})`;
    search.setCustomValidity("");
    if (focus) search.focus();
    close();
    return true;
  }

  search.addEventListener("focus", () => open());
  search.addEventListener("click", () => {
    if (list.hidden) open();
  });
  search.addEventListener("input", () => {
    hidden.value = "";
    search.setCustomValidity("Choose a country from the list.");
    open(search.value);
    highlight(visible.length ? 0 : -1);
  });
  search.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (list.hidden) open();
      if (visible.length) highlight((activeIndex + (event.key === "ArrowDown" ? 1 : -1) + visible.length) % visible.length);
    } else if (event.key === "Enter" && !list.hidden) {
      event.preventDefault();
      if (visible.length) selectCode(visible[activeIndex < 0 ? 0 : activeIndex].code);
    } else if (event.key === "Escape" && !list.hidden) {
      event.preventDefault();
      selectCode(lastCode);
    } else if (event.key === "Tab") {
      close();
    }
  });
  toggle.addEventListener("click", () => {
    if (list.hidden) {
      search.focus();
      open();
    } else close();
  });
  root.addEventListener("focusout", (event) => {
    if (!root.contains(event.relatedTarget)) close();
  });
  document.addEventListener("pointerdown", (event) => {
    if (!root.contains(event.target)) close();
  });

  selectCode(hidden.value, false);
  return { close, selectCode };
}
