import axios from 'axios';

async function test() {
    const url = process.env.APP_URL + '/api/groups';
    console.log("Testing URL:", url);
    try {
        const response = await axios.get(url);
        console.log("Success! Status:", response.status);
    } catch (error) {
        console.log("Error status:", error.response?.status);
        console.log("Error message:", error.message);
    }
}

test();
