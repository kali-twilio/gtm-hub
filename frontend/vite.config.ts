import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	server: {
		proxy: {
			'/api':           'http://localhost:5001',
			'/auth':          'http://localhost:5001',
			'/oauth2callback':'http://localhost:5001',
			'/logout':        'http://localhost:5001',
			'/simulate':      'http://localhost:5001',
		}
	}
});
