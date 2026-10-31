import {createRoot} from 'react-dom/client';
import {App} from './App.jsx';
import {createClient,selectPreview} from './api.js';
let storage;try{storage=globalThis.sessionStorage;}catch{}
const client=createClient({preview:selectPreview(globalThis.location,storage),storage});
createRoot(document.getElementById('root')).render(<App client={client}/>);
