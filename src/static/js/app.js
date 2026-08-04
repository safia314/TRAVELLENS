async function loadHotels() {
    const response = await fetch("/hotels");
    const hotels = await response.json();
    const container = document.getElementById("hotels");
    container.innerHTML = "";

    hotels.forEach(hotel => {
        container.innerHTML += `

            <div class="hotel-card">
                <img src="${hotel.image_url}" alt="${hotel.name}">

                <h3>${hotel.name}</h3>

                <p><strong>Website:</strong> ${hotel.website}</p>

                <p><strong>Price:</strong> ${hotel.price ?? "-"} ${hotel.currency ?? ""}</p>

                <p><strong>Rating:</strong> ⭐ ${hotel.rating ?? "-"}</p>

                <p><strong>Reviews:</strong> ${hotel.reviews ?? "-"}</p>

                <a href="${hotel.hotel_url}" target="_blank">
                    View Hotel
                </a>
            </div>
        `;
    });
}


async function askAI(){
    const prompt = document.getElementById("prompt").value;

    if(prompt.trim()===""){
        return;
    }

    const button = document.getElementById("chat-btn");
    const responseBox = document.getElementById("response");

    button.disabled = true;
    responseBox.innerHTML = "Thinking...";

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
        responseBox.innerHTML = data.response;

    }catch(error){
        responseBox.innerHTML = "An error occurred... Please try again";

    }finally{
        button.disabled = false;
    }
}


document.getElementById("chat-btn").addEventListener("click",askAI);
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