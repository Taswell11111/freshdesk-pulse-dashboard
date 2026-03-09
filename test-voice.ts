import axios from 'axios';

async function test() {
    try {
        const response = await axios.post('http://localhost:3000/api/ai/voice-briefing', {
            dataSummary: "We have a total of 100 active tickets. 50 are currently in Open status. Crucially, 10 tickets are older than 5 days. Our top groups are Group A with 40 tickets."
        });
        console.log("Success!");
    } catch (e: any) {
        console.error("Failed:", e.response?.data || e.message);
    }
}

test();
