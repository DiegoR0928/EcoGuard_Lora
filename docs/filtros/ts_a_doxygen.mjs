/**
 * Filtro de entrada de Doxygen para TypeScript y componentes Svelte (FILTER_PATTERNS del Doxyfile).
 *
 * Doxygen no tiene un analizador de TypeScript ni de Svelte. Este filtro analiza el archivo con el
 * compilador de TypeScript instalado en frontend/node_modules y escribe en la salida estándar
 * declaraciones equivalentes en C++, que Doxygen sí entiende:
 *
 * - Cada archivo es un espacio de nombres según su ruta (frontend::lib::api,
 *   frontend::routes::monitoreo::page). Su documentación es el comentario @file de un módulo .ts o el
 *   comentario <!-- @component --> de un componente .svelte.
 * - De un componente .svelte se toma el bloque <script>; sus props ($props()) forman la estructura Props.
 * - Las interfaces se vuelven estructuras y los alias de tipo, `using`.
 * - Las funciones se escriben como "Tipo f(...)"; si el tipo lleva | o ?, va al final (auto f(...) -> Tipo).
 *   Sin tipo declarado: void o Promise<void> si no devuelven nada, y si no, `function f(...)` o
 *   `async function f(...)`. Lo que un módulo no exporta queda `static`.
 * - Los comentarios sin @brief lo reciben en su primer párrafo, para que aparezcan en los resúmenes.
 * - En los tipos de variables y campos, | ? y las llaves se sustituyen por equivalentes Unicode (∣ ？ ｛ ｝),
 *   porque Doxygen los descarta; la hoja de estilo LaTeX los vuelve a mostrar como los originales.
 * - Los cuerpos se omiten y cada declaración queda en su línea original, para que las advertencias de
 *   Doxygen señalen la línea correcta.
 *
 * Uso: node ts_a_doxygen.mjs ruta/al/archivo.ts|.svelte
 */
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const aqui = path.dirname(fileURLToPath(import.meta.url));
/** Carpeta src/ del panel: las rutas de los espacios de nombres parten de aquí. */
const RAIZ_SRC = path.resolve(aqui, '../../frontend/src');
const ts = createRequire(path.resolve(aqui, '../../frontend/package.json'))('typescript');

/** Longitud máxima de un valor inicial que se muestra completo. */
const MAX_INICIAL = 60;

const archivo = path.resolve(process.argv[2]);
const original = readFileSync(archivo, 'utf8').replace(/\r\n/g, '\n');
const esSvelte = archivo.endsWith('.svelte');

// En un componente solo se analiza el <script>; el resto se cambia por espacios para conservar las posiciones
let codigo = original;
if (esSvelte) {
	const script = /<script\b(?![^>]*\bmodule\b)[^>]*>([\s\S]*?)<\/script>/.exec(original);
	const inicio = script ? script.index + script[0].indexOf('>') + 1 : 0;
	const fin = script ? inicio + script[1].length : 0;
	codigo = [...original].map((c, i) => (c === '\n' || (i >= inicio && i < fin) ? c : ' ')).join('');
}

const fuente = ts.createSourceFile(archivo, codigo, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
const lineas = original.split('\n');
const salida = lineas.map(() => []);
const linea = (pos) => fuente.getLineAndCharacterOfPosition(pos).line;
const emitir = (n, texto) => salida[n].push(texto);

/** Espacio de nombres del archivo según su ruta dentro de src/, p. ej. frontend::routes::monitoreo::page. */
function espacioDeNombres() {
	const partes = path.relative(RAIZ_SRC, archivo).split(path.sep);
	const ultimo = partes.pop().replace(/(\.svelte)?\.ts$|\.svelte$/, '').replace(/^\+/, '');
	return ['frontend', ...partes, ultimo].map((p) => p.replace(/\W/g, '_')).join('::');
}

/** Junta un fragmento en una línea y cambia las comillas simples por tipográficas, que Doxygen conserva. */
function normalizar(texto) {
	return texto
		.replace(/\s+/g, ' ')
		.trim()
		.replace(/'((?:\\.|[^'\\])*)'/g, '‘$1’');
}

/** Tipo de un parámetro o de retorno: Doxygen los conserva tal cual. */
const tipoFuncion = (nodo) => normalizar(nodo.getText());

/** Tipo de una variable o campo: se sustituyen los caracteres que Doxygen descarta en las variables. */
function tipoVariable(nodo) {
	let nivel = 0;
	return [...normalizar(nodo.getText()).replace(/=>/g, '⇒')]
		.map((c) => {
			if (c === '<') nivel++;
			if (c === '>') nivel--;
			const equivalentes = { '|': '∣', '?': '？', '{': '｛', '}': '｝', ';': '；', '(': '（', ')': '）' };
			if (c === ',' && nivel === 0) return '，';
			return equivalentes[c] ?? c;
		})
		.join('');
}

/** Verdadero si la expresión contiene una plantilla `...` o una expresión regular, que se resumen. */
function esComplejo(nodo) {
	if (ts.isRegularExpressionLiteral(nodo) || ts.isTemplateExpression(nodo) || ts.isNoSubstitutionTemplateLiteral(nodo)) return true;
	return ts.forEachChild(nodo, esComplejo) ?? false;
}

/** Resume un valor inicial: completo si es corto; si no, Llamada(…), […] o {…}. */
function valorInicial(nodo) {
	const texto = nodo.getText().replace(/\s+/g, ' ').trim();
	if (texto.length <= MAX_INICIAL && !esComplejo(nodo)) {
		return texto.replace(/'((?:\\.|[^'\\])*)'/g, (_, s) => `"${s.replace(/"/g, '\\"')}"`);
	}
	if (ts.isCallExpression(nodo)) {
		const genericos = nodo.typeArguments ? `<${nodo.typeArguments.map(tipoFuncion).join(', ')}>` : '';
		return `${nodo.expression.getText()}${genericos}(…)`;
	}
	if (ts.isObjectLiteralExpression(nodo)) return '{…}';
	if (ts.isArrayLiteralExpression(nodo)) return '[…]';
	if (ts.isAsExpression(nodo)) return valorInicial(nodo.expression);
	return '';
}

/** Comentario /** *\/ que precede a un nodo (el último, si hay varios), salvo el de @file. */
function comentarioDe(nodo) {
	const rangos = ts.getLeadingCommentRanges(codigo, nodo.pos) ?? [];
	const docs = rangos.filter((r) => codigo.startsWith('/**', r.pos) && !codigo.slice(r.pos, r.end).includes('@file'));
	return docs.at(-1);
}

/**
 * Copia a la salida el comentario de documentación de un nodo, en sus líneas originales. Si no trae
 * @brief, se le agrega al primer párrafo: así Doxygen lo muestra también en los resúmenes.
 */
function emitirComentario(nodo) {
	const rango = comentarioDe(nodo);
	if (!rango) return false;
	let texto = codigo.slice(rango.pos, rango.end);
	if (!/@brief\b/.test(texto)) texto = texto.replace(/^\/\*\*(\s*\n\s*\*)?\s*/, (inicio) => `${inicio}@brief `);
	texto.split('\n').forEach((parte, i) => emitir(linea(rango.pos) + i, parte));
	return true;
}

const exportado = (nodo) => (nodo.modifiers ?? []).some((m) => m.kind === ts.SyntaxKind.ExportKeyword);
const asincrono = (nodo) => (nodo.modifiers ?? []).some((m) => m.kind === ts.SyntaxKind.AsyncKeyword);
/** En un módulo .ts lo no exportado es privado del módulo: se marca static. En un componente no aplica. */
const estatico = (nodo) => (!esSvelte && !exportado(nodo) ? 'static ' : '');

function parametro(p) {
	const tipo = p.type ? tipoFuncion(p.type) : 'any';
	const defecto = p.initializer ? ` = ${valorInicial(p.initializer) || '…'}` : p.questionToken ? ' = undefined' : '';
	return `${tipo} ${p.dotDotDotToken ? '...' : ''}${p.name.getText().replace(/\s+/g, ' ')}${defecto}`;
}

/** Verdadero si la función devuelve un valor (return con expresión, o flecha con expresión). */
function devuelveValor(fn) {
	if (!fn.body) return true;
	if (!ts.isBlock(fn.body)) return true;
	const buscar = (nodo) => {
		if (ts.isFunctionLike(nodo)) return false; // Los return de funciones internas no cuentan
		if (ts.isReturnStatement(nodo) && nodo.expression) return true;
		return ts.forEachChild(nodo, buscar) ?? false;
	};
	return ts.forEachChild(fn.body, buscar) ?? false;
}

/** Verdadero si Doxygen conserva el tipo escrito antes del nombre: sin | ? ni paréntesis fuera de <>. */
function tipoSimple(tipo) {
	let sinGenericos = tipo;
	while (/<[^<>]*>/.test(sinGenericos)) sinGenericos = sinGenericos.replace(/<[^<>]*>/g, '');
	return !/[|?()[\]{}=,]/.test(sinGenericos);
}

/**
 * Declaración C++ de una función, método o función flecha. Sin tipo de retorno declarado: si no
 * devuelve nada se muestra void (o Promise<void> si es async); si devuelve algo, `function`. Los
 * tipos que Doxygen no conserva antes del nombre (con | o ?) van al final: auto f() -> Tipo.
 */
function firma(nombre, fn, prefijo) {
	const parametros = fn.parameters.map(parametro).join(', ');
	let tipo = fn.type ? tipoFuncion(fn.type) : null;
	if (!tipo && !devuelveValor(fn)) tipo = asincrono(fn) ? 'Promise<void>' : 'void';
	if (!tipo) return `${prefijo}${asincrono(fn) ? 'async ' : ''}function ${nombre}(${parametros});`;
	if (tipoSimple(tipo)) return `${prefijo}${tipo} ${nombre}(${parametros});`;
	// Entre paréntesis, Doxygen no confunde un tipo función como () => void con una función que no devuelve nada
	return `${prefijo}auto ${nombre}(${parametros}) -> ${tipo.includes('=>') ? `(${tipo})` : tipo};`;
}

const esLlamadaA = (nodo, nombre) => nodo && ts.isCallExpression(nodo) && nodo.expression.getText() === nombre;
const esFuncion = (nodo) => nodo && (ts.isArrowFunction(nodo) || ts.isFunctionExpression(nodo));

/** Props de un componente: let { a, b }: { a: T; b: U } = $props() se vuelve struct Props { T a; U b; }. */
function props(sentencia, declaracion) {
	if (!emitirComentario(sentencia)) emitir(linea(sentencia.getStart()), '/** @brief Props (propiedades) que recibe el componente. */');
	emitir(linea(sentencia.getStart()), 'struct Props {');
	const tipos = new Map();
	if (declaracion.type && ts.isTypeLiteralNode(declaracion.type)) {
		for (const miembro of declaracion.type.members) tipos.set(miembro.name.getText(), miembro);
	}
	for (const elemento of declaracion.name.elements) {
		const nombre = (elemento.propertyName ?? elemento.name).getText();
		const miembro = tipos.get(nombre);
		const conComentario = [elemento, miembro].find((n) => n && comentarioDe(n));
		if (conComentario) emitirComentario(conComentario);
		const tipo = miembro?.type ? tipoVariable(miembro.type) : 'auto';
		const defecto = elemento.initializer ? ` = ${valorInicial(elemento.initializer)}` : '';
		emitir(linea((conComentario ?? elemento).getStart()), `${tipo} ${nombre}${defecto};`);
	}
	emitir(linea(sentencia.getEnd()), '};');
}

function variable(sentencia, declaracion, primera) {
	if (primera) emitirComentario(sentencia);
	const nombre = declaracion.name.getText();
	const n = linea(declaracion.getStart());
	if (esFuncion(declaracion.initializer)) {
		emitir(n, firma(nombre, declaracion.initializer, estatico(sentencia)));
		return;
	}
	const constante = sentencia.declarationList.flags & ts.NodeFlags.Const ? 'const' : 'let';
	const tipo = declaracion.type ? ` ${tipoVariable(declaracion.type)}` : '';
	const inicial = declaracion.initializer ? valorInicial(declaracion.initializer) : '';
	emitir(n, `${estatico(sentencia)}${constante}${tipo} ${nombre}${inicial ? ` = ${inicial}` : ''};`);
}

function interfaz(nodo) {
	emitirComentario(nodo);
	const bases = (nodo.heritageClauses ?? []).flatMap((h) => h.types.map((t) => `public ${t.getText()}`));
	emitir(linea(nodo.getStart()), `struct ${nodo.name.text}${bases.length ? ` : ${bases.join(', ')}` : ''} {`);
	for (const miembro of nodo.members) {
		emitirComentario(miembro);
		const nombre = miembro.name?.getText() ?? '';
		const n = linea(miembro.getStart());
		if (ts.isMethodSignature(miembro)) emitir(n, firma(nombre, miembro, ''));
		else if (miembro.type) emitir(n, `${tipoVariable(miembro.type)}${miembro.questionToken ? ' ∣ undefined' : ''} ${nombre};`);
	}
	emitir(linea(nodo.getEnd()), '};');
}

// Documentación del espacio de nombres: <!-- @component --> en un componente, /** @file */ en un módulo
const espacio = espacioDeNombres();
let apertura = 0;
const componente = esSvelte && /<!--\s*@component\b([\s\S]*?)-->/.exec(original);
const modulo = !esSvelte && /\/\*\*(?:(?!\*\/)[\s\S])*?@file[\s\S]*?\*\//.exec(original);
if (componente) {
	const n = original.slice(0, componente.index).split('\n').length - 1;
	const texto = componente[1].split('\n');
	texto.forEach((t, i) => emitir(n + i, (i === 0 ? '/** ' : '') + t + (i === texto.length - 1 ? ' */' : '')));
	apertura = n + texto.length - 1;
} else if (modulo) {
	const n = original.slice(0, modulo.index).split('\n').length - 1;
	const texto = modulo[0].replace(/^[ \t]*\*?[ \t]*@file\b.*\n/m, '').split('\n');
	texto.forEach((t, i) => emitir(n + i, t));
	apertura = n + texto.length - 1;
}
emitir(apertura, `namespace ${espacio} {`);

for (const sentencia of fuente.statements) {
	if (ts.isFunctionDeclaration(sentencia) && sentencia.name) {
		emitirComentario(sentencia);
		emitir(linea(sentencia.getStart()), firma(sentencia.name.text, sentencia, estatico(sentencia)));
	} else if (ts.isVariableStatement(sentencia)) {
		sentencia.declarationList.declarations.forEach((declaracion, i) => {
			if (ts.isObjectBindingPattern(declaracion.name) && esLlamadaA(declaracion.initializer, '$props')) {
				props(sentencia, declaracion);
			} else if (ts.isIdentifier(declaracion.name)) {
				variable(sentencia, declaracion, i === 0);
			}
		});
	} else if (ts.isInterfaceDeclaration(sentencia)) {
		interfaz(sentencia);
	} else if (ts.isTypeAliasDeclaration(sentencia)) {
		emitirComentario(sentencia);
		emitir(linea(sentencia.getStart()), `using ${sentencia.name.text} = ${tipoFuncion(sentencia.type)};`);
	}
}
emitir(lineas.length - 1, '}');

process.stdout.write(salida.map((partes) => partes.join(' ')).join('\n') + '\n');
