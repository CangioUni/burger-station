import re

with open("static/index.html", "r") as f:
    html = f.read()

# I will use a series of string replacements to modify each modal individually to ensure I get the exact structure right.

# 1. table-modal
# Currently:
# <div class="bg-gray-800 p-8 rounded-lg w-1/3 min-w-[400px] border border-gray-600">
#   <h2 class="modal-title mb-4 border-b border-gray-600 pb-2">Seleziona Tavolo</h2>
#   <input ...>
#   <div class="grid ..."> ... </div>
#   <div class="flex justify-between space-x-4"> ... buttons ... </div>
# </div>

table_modal_search = """        <div class="bg-gray-800 p-8 rounded-lg w-1/3 min-w-[400px] border border-gray-600">
            <h2 class="modal-title mb-4 border-b border-gray-600 pb-2">Seleziona Tavolo</h2>
            <input type="text" id="table-input"
                class="w-full bg-gray-700 text-white numpad-input font-mono text-center p-4 rounded mb-6 border border-gray-600"
                readonly>
            <div class="grid grid-cols-3 gap-3 mb-6">"""

table_modal_replace = """        <div class="bg-gray-800 p-8 rounded-lg w-1/3 min-w-[400px] border border-gray-600 flex flex-col max-h-[90vh]">
            <h2 class="modal-title mb-4 border-b border-gray-600 pb-2 flex-shrink-0">Seleziona Tavolo</h2>
            <div class="overflow-y-auto flex-grow mb-6">
                <input type="text" id="table-input"
                    class="w-full bg-gray-700 text-white numpad-input font-mono text-center p-4 rounded mb-6 border border-gray-600"
                    readonly>
                <div class="grid grid-cols-3 gap-3">"""

table_modal_search2 = """                <button onclick="tablePress('B')"
                    class="bg-purple-600 p-6 rounded hover:bg-purple-500 numpad-btn shadow text-purple-100">B</button>
            </div>
            <div class="flex justify-between space-x-4">"""

table_modal_replace2 = """                <button onclick="tablePress('B')"
                    class="bg-purple-600 p-6 rounded hover:bg-purple-500 numpad-btn shadow text-purple-100">B</button>
                </div>
            </div>
            <div class="flex justify-between space-x-4 flex-shrink-0 mt-auto">"""

html = html.replace(table_modal_search, table_modal_replace)
html = html.replace(table_modal_search2, table_modal_replace2)


# 2. order-notes-modal
notes_search = """        <div class="bg-gray-800 p-8 rounded-lg w-1/2 border border-gray-600">
            <h2 class="modal-title mb-4 border-b border-gray-600 pb-2">Note all'Ordine</h2>
            <textarea id="order-notes-input"
                class="w-full bg-gray-700 text-white p-4 rounded border border-gray-600 h-32 text-2xl"
                placeholder="Ad esempio: Tutto ben cotto, cliente allergico..."></textarea>
            <div class="flex justify-end space-x-4 mt-6">"""

notes_replace = """        <div class="bg-gray-800 p-8 rounded-lg w-1/2 border border-gray-600 flex flex-col max-h-[90vh]">
            <h2 class="modal-title mb-4 border-b border-gray-600 pb-2 flex-shrink-0">Note all'Ordine</h2>
            <div class="overflow-y-auto flex-grow">
                <textarea id="order-notes-input"
                    class="w-full bg-gray-700 text-white p-4 rounded border border-gray-600 min-h-[8rem] h-32 text-2xl"
                    placeholder="Ad esempio: Tutto ben cotto, cliente allergico..."></textarea>
            </div>
            <div class="flex justify-end space-x-4 mt-6 flex-shrink-0">"""

html = html.replace(notes_search, notes_replace)

# 3. item-modal (The most complex and important one)
item_search = """        <div class="bg-gray-800 p-8 rounded-lg w-1/2">
            <h2 class="modal-title mb-4 border-b border-gray-600 pb-2">Opzioni Articolo</h2>
            <button id="item-modal-combo-edit-btn"
                class="hidden mb-4 bg-purple-600 hover:bg-purple-500 w-full py-3 rounded text-xl font-bold shadow-lg border-2 border-purple-500">
                Modifica Scelte Menu
            </button>
            <div id="item-modal-notes-section" class="mb-4">"""

item_replace = """        <div class="bg-gray-800 p-8 rounded-lg w-1/2 flex flex-col max-h-[90vh]">
            <h2 class="modal-title mb-4 border-b border-gray-600 pb-2 flex-shrink-0">Opzioni Articolo</h2>
            <div class="overflow-y-auto flex-grow pr-2">
                <button id="item-modal-combo-edit-btn"
                    class="hidden mb-4 bg-purple-600 hover:bg-purple-500 w-full py-3 rounded text-xl font-bold shadow-lg border-2 border-purple-500 flex-shrink-0">
                    Modifica Scelte Menu
                </button>
                <div id="item-modal-notes-section" class="mb-4">"""

item_search2 = """                <div class="grid gap-2" id="item-ingredients-grid">
                </div>
            </div>
            <div id="item-modal-discount-section" class="flex justify-between items-center mt-6">"""

item_replace2 = """                <div class="grid gap-2" id="item-ingredients-grid">
                </div>
            </div>
            </div> <!-- Close scrollable content -->
            <div id="item-modal-discount-section" class="flex justify-between items-center mt-6 flex-shrink-0 border-t border-gray-600 pt-4">"""

item_search3 = """                </div>
            </div>

            <div class="flex justify-end space-x-4 mt-6">
                <button id="item-modal-combo-cancel-btn" onclick="closeComboIngredientModal()"
                    class="hidden bg-gray-600 px-6 py-2 rounded modal-btn">Annulla</button>"""

item_replace3 = """                </div>
            </div>

            <div class="flex justify-end space-x-4 mt-4 flex-shrink-0">
                <button id="item-modal-combo-cancel-btn" onclick="closeComboIngredientModal()"
                    class="hidden bg-gray-600 px-6 py-2 rounded modal-btn">Annulla</button>"""

html = html.replace(item_search, item_replace)
html = html.replace(item_search2, item_replace2)
html = html.replace(item_search3, item_replace3)

# 4. item-discount-modal
item_disc_search = """        <div class="bg-gray-800 p-8 rounded-lg w-1/3 min-w-[400px]">
            <h2 class="modal-title mb-4 border-b border-gray-600 pb-2">Imposta Sconto Articolo</h2>

            <div class="flex justify-between items-end mb-4">"""

item_disc_replace = """        <div class="bg-gray-800 p-8 rounded-lg w-1/3 min-w-[400px] flex flex-col max-h-[90vh]">
            <h2 class="modal-title mb-4 border-b border-gray-600 pb-2 flex-shrink-0">Imposta Sconto Articolo</h2>

            <div class="overflow-y-auto flex-grow mb-6">
                <div class="flex justify-between items-end mb-4">"""

item_disc_search2 = """            <div class="flex justify-between text-3xl font-bold mb-6 text-green-400">
                <span>Nuovo Prezzo:</span>
                <span id="item-disc-total">€0.00</span>
            </div>

            <div class="flex justify-end space-x-4 border-t border-gray-600 pt-4">"""

item_disc_replace2 = """            <div class="flex justify-between text-3xl font-bold mb-2 text-green-400">
                <span>Nuovo Prezzo:</span>
                <span id="item-disc-total">€0.00</span>
            </div>
            </div>

            <div class="flex justify-end space-x-4 border-t border-gray-600 pt-4 flex-shrink-0 mt-auto">"""

html = html.replace(item_disc_search, item_disc_replace)
html = html.replace(item_disc_search2, item_disc_replace2)

# 5. discount-modal
disc_search = """        <div class="bg-gray-800 p-8 rounded-lg w-1/3 min-w-[400px]">
            <h2 class="modal-title mb-4 border-b border-gray-600 pb-2">Imposta Sconto</h2>

            <div class="flex justify-between items-end mb-4">"""

disc_replace = """        <div class="bg-gray-800 p-8 rounded-lg w-1/3 min-w-[400px] flex flex-col max-h-[90vh]">
            <h2 class="modal-title mb-4 border-b border-gray-600 pb-2 flex-shrink-0">Imposta Sconto</h2>

            <div class="overflow-y-auto flex-grow mb-6">
                <div class="flex justify-between items-end mb-4">"""

disc_search2 = """            <div class="flex justify-between text-3xl font-bold mb-6 text-green-400">
                <span>Nuovo Totale:</span>
                <span id="disc-total">€0.00</span>
            </div>

            <div class="flex justify-end space-x-4 border-t border-gray-600 pt-4">"""

disc_replace2 = """            <div class="flex justify-between text-3xl font-bold mb-2 text-green-400">
                <span>Nuovo Totale:</span>
                <span id="disc-total">€0.00</span>
            </div>
            </div>

            <div class="flex justify-end space-x-4 border-t border-gray-600 pt-4 flex-shrink-0 mt-auto">"""

html = html.replace(disc_search, disc_replace)
html = html.replace(disc_search2, disc_replace2)

# 6. settings-overlay
settings_search = """        <div class="bg-gray-800 p-8 rounded-lg w-1/2">
            <h2 class="modal-title mb-6 border-b border-gray-600 pb-2">Impostazioni</h2>
            <div class="mb-6 p-5 border border-gray-600 rounded-lg bg-gray-900 shadow-inner">"""

settings_replace = """        <div class="bg-gray-800 p-8 rounded-lg w-1/2 flex flex-col max-h-[90vh]">
            <h2 class="modal-title mb-6 border-b border-gray-600 pb-2 flex-shrink-0">Impostazioni</h2>
            <div class="overflow-y-auto flex-grow pr-2 mb-6">
                <div class="mb-6 p-5 border border-gray-600 rounded-lg bg-gray-900 shadow-inner">"""

settings_search2 = """                <p class="text-sm text-gray-400 mt-1">Imposta il numero da cui ripartire. Non cancellerà lo storico a
                    database.</p>
            </div>
            <div class="flex justify-end space-x-4">"""

settings_replace2 = """                <p class="text-sm text-gray-400 mt-1">Imposta il numero da cui ripartire. Non cancellerà lo storico a
                    database.</p>
            </div>
            </div>
            <div class="flex justify-end space-x-4 flex-shrink-0 mt-auto border-t border-gray-600 pt-4">"""

html = html.replace(settings_search, settings_replace)
html = html.replace(settings_search2, settings_replace2)

# 7. payment-modal
payment_search = """        <div class="bg-gray-800 p-8 rounded-lg w-1/3 min-w-[400px]">
            <div class="flex justify-between items-center mb-4 border-b border-gray-600 pb-2">
                <h2 class="modal-title">Metodo di Pagamento</h2>
                <div class="text-2xl font-bold text-green-400">Totale: <span id="payment-modal-total">€0.00</span></div>
            </div>

            <div class="grid grid-cols-2 gap-4 mb-8 mt-4">"""

payment_replace = """        <div class="bg-gray-800 p-8 rounded-lg w-1/3 min-w-[400px] flex flex-col max-h-[90vh]">
            <div class="flex justify-between items-center mb-4 border-b border-gray-600 pb-2 flex-shrink-0">
                <h2 class="modal-title">Metodo di Pagamento</h2>
                <div class="text-2xl font-bold text-green-400">Totale: <span id="payment-modal-total">€0.00</span></div>
            </div>

            <div class="overflow-y-auto flex-grow mb-6">
                <div class="grid grid-cols-2 gap-4 mt-4">"""

payment_search2 = """                    class="bg-blue-500 text-white py-6 rounded font-bold text-2xl border-4 border-transparent shadow-lg">BANCOMAT</button>
            </div>

            <div class="flex justify-between space-x-4 border-t border-gray-600 pt-6">"""

payment_replace2 = """                    class="bg-blue-500 text-white py-6 rounded font-bold text-2xl border-4 border-transparent shadow-lg">BANCOMAT</button>
                </div>
            </div>

            <div class="flex justify-between space-x-4 border-t border-gray-600 pt-6 flex-shrink-0 mt-auto">"""

html = html.replace(payment_search, payment_replace)
html = html.replace(payment_search2, payment_replace2)

# 8. varie-modal
varie_search = """        <div class="bg-gray-800 p-8 rounded-lg w-1/3 min-w-[400px]">
            <h2 class="modal-title mb-4 border-b border-gray-600 pb-2">Aggiungi VARIE</h2>

            <div class="mb-4">"""

varie_replace = """        <div class="bg-gray-800 p-8 rounded-lg w-1/3 min-w-[400px] flex flex-col max-h-[90vh]">
            <h2 class="modal-title mb-4 border-b border-gray-600 pb-2 flex-shrink-0">Aggiungi VARIE</h2>

            <div class="overflow-y-auto flex-grow mb-6">
                <div class="mb-4">"""

varie_search2 = """                <button onclick="numpadPressVarie(0)" class="bg-gray-600 p-4 rounded hover:bg-gray-500">0</button>
                <button onclick="numpadPressVarie('.')" class="bg-gray-600 p-4 rounded hover:bg-gray-500">.</button>
            </div>

            <div class="flex justify-end space-x-4 border-t border-gray-600 pt-4">"""

varie_replace2 = """                <button onclick="numpadPressVarie(0)" class="bg-gray-600 p-4 rounded hover:bg-gray-500">0</button>
                <button onclick="numpadPressVarie('.')" class="bg-gray-600 p-4 rounded hover:bg-gray-500">.</button>
                </div>
            </div>

            <div class="flex justify-end space-x-4 border-t border-gray-600 pt-4 flex-shrink-0 mt-auto">"""

html = html.replace(varie_search, varie_replace)
html = html.replace(varie_search2, varie_replace2)

with open("static/index.html", "w") as f:
    f.write(html)
