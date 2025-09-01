// Helper function to add balloon data directly (no AI call needed)
function addDirectBalloonData(parameterName, value, number, position) {
    // Create balloon data object
    const balloonItem = {
        parameter: parameterName,
        value: value,
        number: number,
        ...position
    };
    
    // Add to balloon data array
    balloonData.push(balloonItem);
    
    // Create table row
    const tr = document.createElement('tr');
    tr.dataset.balloonNumber = number;
    tr.innerHTML = `
        <td class="px-4 py-3"><div class="balloon-table">${number}</div></td>
        <td class="px-4 py-3 font-medium">${parameterName}</td>
        <td class="px-4 py-3">${value}</td>
        <td class="px-4 py-3 text-center">
            <button class="remove-balloon-btn text-red-500 hover:text-red-700" title="Remove item">&times;</button>
        </td>`;
    reportTableBody.appendChild(tr);
    
    // Show results and hide placeholder
    resultsSection.classList.remove('hidden');
    placeholderText.classList.add('hidden');
    
    // Update balloon positions
    repositionBalloons();
}

// Helper function to fetch value from AI backend
async function fetchValueFromAI(label, number, position) {
    loaderText.textContent = `Finding value for "${label}"...`;
    loader.classList.remove('hidden');

    try {
        const formData = new FormData();
        formData.append('sourceFile', sourceFile);
        formData.append('label', label);

        const response = await fetch(`${backendUrlBase}/get-value-for-label`, { 
            method: 'POST', 
            body: formData 
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to get value from AI');
        }
        
        const data = await response.json();
        
        // Add to balloon data array with position info
        balloonData.push({ ...data, ...position, number });
        
        // Create table row
        const tr = document.createElement('tr');
        tr.dataset.balloonNumber = number;
        tr.innerHTML = `
            <td class="px-4 py-3"><div class="balloon-table">${number}</div></td>
            <td class="px-4 py-3 font-medium">${data.parameter}</td>
            <td class="px-4 py-3">${data.value}</td>
            <td class="px-4 py-3 text-center">
                <button class="remove-balloon-btn text-red-500 hover:text-red-700" title="Remove item">&times;</button>
            </td>`;
        reportTableBody.appendChild(tr);
        
        // Show results and hide placeholder
        resultsSection.classList.remove('hidden');
        placeholderText.classList.add('hidden');
        
        // Update balloon positions
        repositionBalloons();
        
    } catch (error) {
        showError(`Could not get data for "${label}": ${error.message}`);
        balloonCounter--; // Decrement counter since we failed
    } finally {
        loader.classList.add('hidden');
    }
}
