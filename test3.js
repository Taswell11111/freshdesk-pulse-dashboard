import axios from 'axios';

async function test() {
    try {
        const response = await axios.get(`https://ecomplete.freshdesk.com/api/v2/groups`, {
            headers: { 'Authorization': 'Basic dW5kZWZpbmVkOlg=' }
        });
        console.log("Success:", response.data);
    } catch (error) {
        console.log("Error status:", error.response?.status);
        console.log("Error message:", error.message);
    }
}

test();
