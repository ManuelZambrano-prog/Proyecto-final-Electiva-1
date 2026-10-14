/* ==========================================================================
   INTERACTIVIDAD DE LA TIENDA
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {
    initPlantCalculator();
    initCheckoutCalculator();
});

/* --------------------------------------------------------------------------
   2. CALCULADORA Y RECOMENDADOR DE KIT SEGÚN PLANTAS EN CASA
   -------------------------------------------------------------------------- */
function initPlantCalculator() {
    const calcSlider = document.getElementById('calc-plant-count');
    const calcCountDisplay = document.getElementById('calc-count-display');
    const recKitName = document.getElementById('rec-kit-name');
    const recKitDesc = document.getElementById('rec-kit-desc');
    const recKitPrice = document.getElementById('rec-kit-price');
    const recKitBtn = document.getElementById('rec-kit-btn');

    if (!calcSlider || !recKitName) return;

    function evaluateRecommendation() {
        const count = parseInt(calcSlider.value, 10);
        calcCountDisplay.textContent = count === 1 ? '1 Planta' : `${count} Plantas`;

        if (count <= 3) {
            recKitName.textContent = 'Kit Balcón & Ventana (1 - 3 plantas)';
            recKitDesc.textContent = 'Incluye 1 electroválvula, 5m de manguera y servomotor compacto.';
            recKitPrice.textContent = '$99.000 COP/mes';
            recKitBtn.href = '/checkout/?kit=kit-balcon-ventana';
        } else if (count <= 8) {
            recKitName.textContent = 'Kit Hogar Verde Pro (4 - 8 plantas) ⭐ Recomendado';
            recKitDesc.textContent = 'Incluye 1 electroválvula, 12m de microtubo, servomotor y sensores de humedad y temperatura.';
            recKitPrice.textContent = '$169.000 COP/mes';
            recKitBtn.href = '/checkout/?kit=kit-hogar-verde-pro';
        } else {
            recKitName.textContent = 'Kit Jardín Interior Smart (hasta 16 plantas)';
            recKitDesc.textContent = 'Incluye 1 electroválvula modular, 25m de tubería y servomotor de alta durabilidad.';
            recKitPrice.textContent = '$259.000 COP/mes';
            recKitBtn.href = '/checkout/?kit=kit-jardin-interior-smart';
        }
    }

    calcSlider.addEventListener('input', evaluateRecommendation);
    evaluateRecommendation();
}

/* --------------------------------------------------------------------------
   3. CÁLCULO DINÁMICO EN CHECKOUT
   -------------------------------------------------------------------------- */
function initCheckoutCalculator() {
    const kitSelect = document.getElementById('id_kit');
    const chkServo = document.getElementById('id_servo_extra');
    const chkSensores = document.getElementById('id_sensores_extra');
    const totalDisplay = document.getElementById('summary-total-display');
    const kitNameDisplay = document.getElementById('summary-kit-name');
    const kitPriceDisplay = document.getElementById('summary-kit-price');
    const extraServoRow = document.getElementById('summary-extra-servo');
    const extraSensoresRow = document.getElementById('summary-extra-sensores');

    if (!kitSelect || !totalDisplay) return;

    // Precios de kits (asociados por texto o valor)
    const preciosKits = {
        '1': { nombre: 'Kit Balcón & Ventana', precio: 99000 },
        '2': { nombre: 'Kit Hogar Verde Pro', precio: 169000 },
        '3': { nombre: 'Kit Jardín Interior Smart', precio: 259000 }
    };

    function recalculateTotal() {
        const kitId = kitSelect.value;
        const kitInfo = preciosKits[kitId] || { nombre: 'Kit Seleccionado', precio: 169000 };

        let total = kitInfo.precio;
        if (kitNameDisplay) kitNameDisplay.textContent = kitInfo.nombre;
        if (kitPriceDisplay) kitPriceDisplay.textContent = `$${kitInfo.precio.toLocaleString('es-CO')}`;

        if (chkServo && chkServo.checked) {
            total += 35000;
            if (extraServoRow) extraServoRow.style.display = 'flex';
        } else {
            if (extraServoRow) extraServoRow.style.display = 'none';
        }

        if (chkSensores && chkSensores.checked) {
            total += 28000;
            if (extraSensoresRow) extraSensoresRow.style.display = 'flex';
        } else {
            if (extraSensoresRow) extraSensoresRow.style.display = 'none';
        }

        totalDisplay.textContent = `$${total.toLocaleString('es-CO')}`;
    }

    kitSelect.addEventListener('change', recalculateTotal);
    if (chkServo) chkServo.addEventListener('change', recalculateTotal);
    if (chkSensores) chkSensores.addEventListener('change', recalculateTotal);

    recalculateTotal();
}
