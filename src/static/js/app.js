function formatDate(dateStr) {
    if (!dateStr) return null;
    const d = new Date(dateStr);
    if (isNaN(d)) return dateStr;
    return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

function buildAmenityBadges(amenities) {
    if (!amenities) return "";

    // amenities is stored as a raw string; split on common delimiters
    const items = amenities
        .split(/,|\||;/)
        .map(a => a.trim())
        .filter(a => a.length > 0);

    if (items.length === 0) return "";

    const badges = items
        .map(item => `<span class="amenity-badge">${item}</span>`)
        .join("");

    return `<div class="amenity-list">${badges}</div>`;
}

function buildPriceBlock(hotel) {
    const hasDiscount = hotel.discount_percentage && Number(hotel.discount_percentage) > 0;
    const hasOriginal = hotel.original_price && Number(hotel.original_price) !== Number(hotel.price);

    let priceHtml = `<span class="current-price">${hotel.price ?? "-"} ${hotel.currency ?? ""}</span>`;

    if (hasOriginal) {
        priceHtml = `<span class="original-price">${hotel.original_price} ${hotel.currency ?? ""}</span> ` + priceHtml;
    }

    if (hasDiscount) {
        priceHtml += ` <span class="discount-badge">-${hotel.discount_percentage}%</span>`;
    }

    const taxLine = hotel.is_tax_included === false
        ? `<p class="tax-note">+ ${hotel.tax_amount ?? "tax"} ${hotel.currency ?? ""} taxes (not included)</p>`
        : `<p class="tax-note tax-included">Taxes included</p>`;

    return `<div class="price-block">${priceHtml}</div>${taxLine}`;
}

function populateCityUI(hotels) {
    const cities = [...new Set(hotels.map(h => h.city).filter(Boolean))].sort();

    // Header trip-info line
    const tripCitiesEl = document.getElementById("trip-cities");
    if (cities.length === 0) {
        tripCitiesEl.textContent = "📍 No cities crawled yet";
    } else if (cities.length === 1) {
        tripCitiesEl.textContent = `📍 ${cities[0]}`;
    } else {
        tripCitiesEl.textContent = `📍 ${cities.length} cities: ${cities.join(", ")}`;
    }

    // City dropdown (preserve current selection if still valid)
    const select = document.getElementById("city-select");
    const currentValue = select.value;
    select.innerHTML = `<option value="">All cities</option>`;

    cities.forEach(city => {
        const option = document.createElement("option");
        option.value = city;
        option.textContent = city;
        select.appendChild(option);
    });

    if (cities.includes(currentValue)) {
        select.value = currentValue;
    }
}

async function loadHotels() {
    const response = await fetch("/hotels");
    const hotels = await response.json();
    populateCityUI(hotels);
    renderHotels(hotels);
}

function renderHotels(hotels) {
    const container = document.getElementById("hotels");
    container.innerHTML = "";

    if (hotels.length === 0) {
        container.innerHTML = `<p class="no-results">No hotels match your search.</p>`;
        return;
    }

    hotels.forEach(hotel => {
        const checkIn = formatDate(hotel.check_in);
        const checkOut = formatDate(hotel.check_out);

        const stayLine = (checkIn && checkOut)
            ? `<p class="stay-dates">📅 ${checkIn} → ${checkOut}</p>`
            : "";

        const cityLine = hotel.city
            ? `<p class="hotel-city">📍 ${hotel.city}</p>`
            : "";

        container.innerHTML += `

            <div class="hotel-card">
                <img src="${hotel.image_url}" alt="${hotel.name}">

                <h3>${hotel.name}</h3>

                <p><strong>Website:</strong> ${hotel.website}</p>

                ${cityLine}
                ${stayLine}

                ${buildPriceBlock(hotel)}

                <p><strong>Rating:</strong> ⭐ ${hotel.rating ?? "-"}</p>

                <p><strong>Reviews:</strong> ${hotel.reviews ?? "-"}</p>

                ${buildAmenityBadges(hotel.amenities)}

                <a href="${hotel.hotel_url}" target="_blank">
                    View Hotel
                </a>
            </div>
        `;
    });
}

async function searchHotels() {
    const params = new URLSearchParams();

    const name = document.getElementById("filter-name").value.trim();
    const city = document.getElementById("city-select").value;
    const minRating = document.getElementById("filter-min-rating").value;
    const maxPrice = document.getElementById("filter-max-price").value;
    const checkIn = document.getElementById("filter-checkin").value;
    const checkOut = document.getElementById("filter-checkout").value;

    if (name) params.append("name", name);
    if (city) params.append("city", city);
    if (minRating) params.append("min_rating", minRating);
    if (maxPrice) params.append("max_price", maxPrice);
    if (checkIn) params.append("check_in", checkIn);
    if (checkOut) params.append("check_out", checkOut);

    const container = document.getElementById("hotels");
    container.innerHTML = `<p class="no-results">Searching...</p>`;

    try {
        const response = await fetch(`/hotels/search?${params.toString()}`);
        const hotels = await response.json();
        renderHotels(hotels);
    } catch (error) {
        container.innerHTML = `<p class="no-results">Something went wrong. Please try again.</p>`;
    }
}

function resetFilters() {
    document.getElementById("filter-name").value = "";
    document.getElementById("city-select").value = "";
    document.getElementById("filter-min-rating").value = "";
    document.getElementById("filter-max-price").value = "";
    document.getElementById("filter-checkin").value = "";
    document.getElementById("filter-checkout").value = "";
    loadHotels();
}

document.getElementById("filter-btn").addEventListener("click", searchHotels);
document.getElementById("filter-reset-btn").addEventListener("click", resetFilters);
document.getElementById("city-select").addEventListener("change", searchHotels);


// ================= CROSS-SITE COMPARE =================

function renderCompareResults(data) {
    const container = document.getElementById("compare-results");

    if (!data.results || data.results.length === 0) {
        container.innerHTML = `<p class="no-results">No matches found. Make sure both Booking and Almosafer have been crawled for this city and dates.</p>`;
        return;
    }

    const summary = `
        <p class="compare-summary">
            ${data.total_matches} hotel(s) found · ${data.matched_across_sites} matched across both sites · ${data.single_site_only} on a single site only
        </p>
    `;

    const rows = data.results.map(match => {
        const listingsHtml = match.listings.map(listing => {
            const isCheapest = listing.website === match.cheapest_website;
            return `
                <div class="compare-listing ${isCheapest ? "cheapest" : ""}">
                    <span class="listing-site">${listing.website}</span>
                    <span class="listing-price">${listing.price ?? "-"} ${listing.currency ?? ""}</span>
                    ${isCheapest ? '<span class="cheapest-badge">Best price</span>' : ""}
                    <a href="${listing.hotel_url}" target="_blank">View</a>
                </div>
            `;
        }).join("");

        const confidenceNote = match.low_confidence
            ? `<span class="low-confidence-badge">⚠ Low-confidence match</span>`
            : "";

        return `
            <div class="compare-card">
                <div class="compare-card-header">
                    <h3>${match.canonical_name}</h3>
                    ${confidenceNote}
                </div>
                ${match.price_spread ? `<p class="price-spread">Price difference: ${match.price_spread} ${match.listings[0]?.currency ?? ""}</p>` : ""}
                <div class="compare-listings">${listingsHtml}</div>
            </div>
        `;
    }).join("");

    container.innerHTML = summary + rows;
}

async function compareHotels() {
    const city = document.getElementById("compare-city").value.trim();
    const checkIn = document.getElementById("compare-checkin").value;
    const checkOut = document.getElementById("compare-checkout").value;

    const container = document.getElementById("compare-results");

    if (!city || !checkIn || !checkOut) {
        container.innerHTML = `<p class="no-results">Please fill in city, check-in, and check-out to compare.</p>`;
        return;
    }

    container.innerHTML = `<p class="no-results">Comparing...</p>`;

    const params = new URLSearchParams({ city, check_in: checkIn, check_out: checkOut });

    try {
        const response = await fetch(`/hotels/compare?${params.toString()}`);

        if (!response.ok) {
            container.innerHTML = `<p class="no-results">Something went wrong. Please try again.</p>`;
            return;
        }

        const data = await response.json();
        renderCompareResults(data);
    } catch (error) {
        container.innerHTML = `<p class="no-results">Something went wrong. Please try again.</p>`;
    }
}

document.getElementById("compare-btn").addEventListener("click", compareHotels);


function appendChatMessage(role, text) {
    const messages = document.getElementById("chat-messages");
    const bubble = document.createElement("div");
    bubble.className = `chat-bubble ${role}`;
    bubble.innerHTML = text;
    messages.appendChild(bubble);
    messages.scrollTop = messages.scrollHeight;
    return bubble;
}

function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

async function askAI(){
    const promptBox = document.getElementById("prompt");
    const prompt = promptBox.value.trim();

    if(prompt===""){
        return;
    }

    const button = document.getElementById("chat-btn");

    appendChatMessage("user", escapeHtml(prompt));
    promptBox.value = "";
    button.disabled = true;

    const thinkingBubble = appendChatMessage("ai thinking", `<span class="dot"></span><span class="dot"></span><span class="dot"></span>`);

    try{

        const response = await fetch("/hotels/chat",{
            method:"POST",

            headers:{
                "Content-Type":"application/json"
            },

            body:JSON.stringify({
                prompt:prompt
            })
        });

        const data = await response.json();
        thinkingBubble.classList.remove("thinking");
        thinkingBubble.innerHTML = data.response;

    }catch(error){
        thinkingBubble.classList.remove("thinking");
        thinkingBubble.classList.add("error");
        thinkingBubble.innerHTML = "⚠ Something went wrong. Please try again.";

    }finally{
        button.disabled = false;
        promptBox.focus();
    }
}


document.getElementById("chat-btn").addEventListener("click",askAI);

document.getElementById("prompt").addEventListener("keydown", function(e) {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        askAI();
    }
});

window.onload=loadHotels;


const chat = document.getElementById("chatWindow");
chat.onmousedown = function(e) {
    let x = e.clientX - chat.offsetLeft;
    let y = e.clientY - chat.offsetTop;

    document.onmousemove = function (e) {
        chat.style.left = (e.clientX - x) + "px";
        chat.style.top = (e.clientY - y) + "px";

        chat.style.right = "auto";
        chat.style.bottom = "auto";
    };

    document.onmouseup = function () {
        document.onmousemove = null;
        document.onmouseup = null;
    };
};


const chatWindow = document.getElementById("chatWindow");
const chatToggle = document.getElementById("chatToggle");
chatWindow.style.display = "none";

chatToggle.onclick = function () {

    if (chatWindow.style.display === "none") {
        chatWindow.style.display = "block";
        chatToggle.innerHTML = "✕";

    } else {
        chatWindow.style.display = "none";
        chatToggle.innerHTML = "🤖";
    }
};