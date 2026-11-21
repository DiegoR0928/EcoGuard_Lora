"""
Filtro de entrada de Doxygen para Dart (FILTER_PATTERNS del Doxyfile).

Doxygen no tiene un analizador de Dart. Este filtro lee un archivo .dart y escribe en la salida
estándar declaraciones equivalentes en C++, que Doxygen sí entiende:

- El archivo es un espacio de nombres (ecoguard_app::pantallas::sos_activo); su documentación es el
  comentario /// que precede a la directiva `library;`.
- Clases, extensiones y mixins se vuelven clases; los miembros que empiezan con _ quedan privados y
  los métodos de las clases abstractas, virtuales (así las implementaciones heredan su documentación).
- Métodos y funciones se escriben como "Tipo f(...)". Si el tipo de retorno es anulable (int?) o un
  registro, va al final (auto f(...) -> Tipo): es la única forma en que Doxygen lo conserva.
- Campos y getters se escriben como variables. En su tipo, ? se sustituye por ？ (U+FF1F), porque
  Doxygen descarta el ? en las variables; la hoja de estilo LaTeX lo vuelve a mostrar como ?.
- Los cuerpos de las funciones se omiten y cada declaración queda en su línea original, para que las
  advertencias de Doxygen señalen la línea correcta del archivo .dart.

Uso: python dart_a_doxygen.py ruta/al/archivo.dart
"""
import bisect
import re
import sys
from pathlib import Path

## Primer espacio de nombres: el nombre del paquete en pubspec.yaml.
PAQUETE = 'ecoguard_app'
## Palabras que pueden preceder al tipo de un campo o variable.
MODIFICADORES = {'static', 'const', 'final', 'late', 'var', 'external', 'covariant', 'abstract'}
## Longitud máxima de un valor inicial que se muestra completo.
MAX_INICIAL = 60


class Fuente:
    """
    @brief Archivo Dart con sus comentarios y cadenas identificados.

    Guarda dos copias del texto del mismo largo que el original: `sin_comentarios`, con los
    comentarios cambiados por espacios, y `estructura`, que además vacía el contenido de las cadenas.
    La segunda permite contar llaves y paréntesis sin confundirse con los que aparecen en el texto.
    """

    def __init__(self, texto):
        """
        @brief Analiza el texto.
        @param texto Contenido del archivo .dart.
        """
        ## Texto original.
        self.texto = texto
        ## Texto sin comentarios.
        self.sin_comentarios = list(texto)
        ## Texto sin comentarios ni contenido de cadenas.
        self.estructura = list(texto)
        ## Comentarios de documentación (///): número de línea → texto del comentario.
        self.docs = {}
        ## Posición en que empieza cada línea.
        self.inicios = [0] + [i + 1 for i, c in enumerate(texto) if c == '\n']
        self._escanear(0, False)
        self.sin_comentarios = ''.join(self.sin_comentarios)
        self.estructura = ''.join(self.estructura)

    def linea(self, pos):
        """
        @brief Número de línea (desde 0) de una posición del texto.
        @param pos Posición en el texto.
        @return Número de línea.
        """
        return bisect.bisect_right(self.inicios, pos) - 1

    def _blanquear(self, copias, a, b):
        """
        @brief Cambia por espacios el texto entre a y b (sin incluir b) en las copias indicadas, salvo los saltos de línea.
        @param copias Listas de caracteres a modificar.
        @param a Posición inicial.
        @param b Posición final.
        """
        for copia in copias:
            for k in range(a, b):
                if copia[k] != '\n':
                    copia[k] = ' '

    def _escanear(self, i, interpolacion):
        """
        @brief Recorre código Dart identificando comentarios y cadenas.
        @param i Posición inicial.
        @param interpolacion Verdadero si se recorre el código de una interpolación ${...}: termina en su llave de cierre.
        @return Posición siguiente al final del recorrido.
        """
        t, n, profundidad = self.texto, len(self.texto), 0
        while i < n:
            if t.startswith('//', i):
                fin = t.find('\n', i)
                fin = n if fin < 0 else fin
                if t.startswith('///', i) and not t.startswith('////', i):
                    self.docs[self.linea(i)] = t[i:fin].strip()
                self._blanquear((self.sin_comentarios, self.estructura), i, fin)
                i = fin
            elif t.startswith('/*', i):
                fin = self._fin_bloque(i)
                self._blanquear((self.sin_comentarios, self.estructura), i, fin)
                i = fin
            elif t[i] in '\'"' or (t[i] in 'rR' and t[i + 1:i + 2] in ('\'', '"') and not (t[i - 1:i].isalnum() or t[i - 1:i] == '_')):
                fin = self._fin_cadena(i)
                self._blanquear((self.estructura,), i + 1, fin - 1)
                i = fin
            else:
                if interpolacion and t[i] == '{':
                    profundidad += 1
                elif interpolacion and t[i] == '}':
                    if profundidad == 0:
                        return i + 1
                    profundidad -= 1
                i += 1
        return i

    def _fin_bloque(self, i):
        """
        @brief Encuentra el final de un comentario de bloque, que en Dart puede anidarse.
        @param i Posición del /* inicial.
        @return Posición siguiente al */ de cierre.
        """
        t, nivel, i = self.texto, 0, i
        while i < len(t):
            if t.startswith('/*', i):
                nivel, i = nivel + 1, i + 2
            elif t.startswith('*/', i):
                nivel, i = nivel - 1, i + 2
                if nivel == 0:
                    return i
            else:
                i += 1
        return len(t)

    def _fin_cadena(self, i):
        """
        @brief Encuentra el final de una cadena: simple, triple o cruda, con interpolaciones ${...}.
        @param i Posición del inicio de la cadena (la comilla o el prefijo r).
        @return Posición siguiente a la comilla de cierre.
        """
        t, n = self.texto, len(self.texto)
        cruda = t[i] in 'rR'
        if cruda:
            i += 1
        comilla = t[i]
        delimitador = comilla * 3 if t.startswith(comilla * 3, i) else comilla
        j = i + len(delimitador)
        while j < n:
            if not cruda and t[j] == '\\':
                j += 2
            elif t.startswith(delimitador, j):
                return j + len(delimitador)
            elif len(delimitador) == 1 and t[j] == '\n':
                return j
            elif not cruda and t.startswith('${', j):
                j = self._escanear(j + 2, True)
            else:
                j += 1
        return n

    def cierre(self, i):
        """
        @brief Encuentra la llave, paréntesis o corchete que cierra al que está en i.
        @param i Posición del carácter de apertura.
        @return Posición del carácter de cierre.
        """
        e, nivel = self.estructura, 0
        for j in range(i, len(e)):
            if e[j] in '([{':
                nivel += 1
            elif e[j] in ')]}':
                nivel -= 1
                if nivel == 0:
                    return j
        return len(e) - 1


class Declaracion:
    """
    @brief Una declaración de Dart delimitada por su encabezado y su final.
    """

    def __init__(self, inicio, fin_encabezado, tipo_fin, fin, cuerpo=None):
        ## Posición del primer carácter.
        self.inicio = inicio
        ## Posición donde termina el encabezado (antes de {, => o ;).
        self.fin_encabezado = fin_encabezado
        ## Cómo termina: 'llave' (cuerpo entre llaves), 'flecha' (=> expresión;) o 'punto_y_coma'.
        self.tipo_fin = tipo_fin
        ## Posición siguiente al final de la declaración.
        self.fin = fin
        ## (apertura, cierre) de las llaves del cuerpo, si las hay.
        self.cuerpo = cuerpo


def declaraciones(f, a, b):
    """
    @brief Divide un bloque de código en declaraciones (nivel superior o cuerpo de una clase).
    @param f Fuente analizada.
    @param a Posición inicial del bloque.
    @param b Posición final del bloque (sin incluir).
    @return Lista de Declaracion.
    """
    e, lista, i = f.estructura, [], a
    while True:
        while i < b and e[i].isspace():
            i += 1
        if i >= b:
            return lista
        inicio, nivel, asignacion, lista_inicial, j = i, 0, False, False, i
        while j < b:
            c = e[j]
            if c in '([':
                nivel += 1
            elif c in ')]':
                nivel -= 1
            elif c == '{' and nivel == 0 and not asignacion:
                cierre = f.cierre(j)
                lista.append(Declaracion(inicio, j, 'llave', cierre + 1, (j, cierre)))
                i = cierre + 1
                break
            elif c == '{':
                nivel += 1
            elif c == '}':
                nivel -= 1
            elif c == ';' and nivel == 0:
                lista.append(Declaracion(inicio, j, 'punto_y_coma', j + 1))
                i = j + 1
                break
            elif c == ':' and nivel == 0 and not asignacion and e[inicio:j].rstrip().endswith(')'):
                lista_inicial = True  # Lista de inicialización de un constructor: Foo(a) : b = a
            elif c == '=' and nivel == 0 and e[j + 1:j + 2] == '>':
                fin = fin_expresion(e, j + 2, b)
                lista.append(Declaracion(inicio, j, 'flecha', fin + 1))
                i = fin + 1
                break
            elif c == '=' and nivel == 0 and e[j + 1:j + 2] != '=' and e[j - 1] not in '=!<>' and not lista_inicial:
                asignacion = True
            j += 1
        else:
            return lista


def fin_expresion(e, i, b):
    """
    @brief Encuentra el punto y coma que termina una expresión, fuera de paréntesis, corchetes y llaves.
    @param e Texto de estructura.
    @param i Posición inicial.
    @param b Límite del bloque.
    @return Posición del punto y coma.
    """
    nivel = 0
    for j in range(i, b):
        if e[j] in '([{':
            nivel += 1
        elif e[j] in ')]}':
            nivel -= 1
        elif e[j] == ';' and nivel == 0:
            return j
    return b - 1


def una_linea(texto):
    """
    @brief Junta un fragmento de código en una sola línea con espacios simples.
    @param texto Fragmento.
    @return El fragmento normalizado.
    """
    return re.sub(r'\s+', ' ', texto).strip()


def sin_anotaciones(texto):
    """
    @brief Quita las anotaciones (@override, @Deprecated(...)) del inicio de un encabezado.
    @param texto Encabezado.
    @return Encabezado sin anotaciones.
    """
    return re.sub(r'^(?:@\w+(?:\.\w+)*(?:\([^()]*\))?\s*)+', '', texto)


def dividir(texto, separador=','):
    """
    @brief Divide un texto por un separador que esté fuera de (), [], {} y <>.
    @param texto Texto a dividir.
    @param separador Carácter separador.
    @return Lista de partes, sin espacios alrededor.
    """
    partes, nivel, actual = [], 0, ''
    for i, c in enumerate(texto):
        if c in '([{':
            nivel += 1
        elif c in ')]}':
            nivel -= 1
        elif c == '<' and i > 0 and (texto[i - 1].isalnum() or texto[i - 1] in '_>?'):
            nivel += 1
        elif c == '>' and nivel > 0 and texto[i - 1:i] != '=':
            nivel -= 1
        if c == separador and nivel == 0:
            partes.append(actual.strip())
            actual = ''
        else:
            actual += c
    if actual.strip():
        partes.append(actual.strip())
    return partes


def tipo_simple(tipo):
    """
    @brief Indica si Doxygen conserva el tipo escrito antes del nombre de una función.
    @param tipo Tipo de retorno en Dart.
    @return True si no tiene ? ni paréntesis fuera de los genéricos <...>.
    """
    while re.search(r'<[^<>]*>', tipo):
        tipo = re.sub(r'<[^<>]*>', '', tipo)
    return not re.search(r'[?()\[\]{}=,|]', tipo)


def tipo_variable(tipo):
    """
    @brief Adapta el tipo de un campo o variable para que Doxygen lo conserve.

    Doxygen descarta los ? de los tipos de las variables y parte los registros (A, B) por la coma;
    se usan los caracteres de ancho completo ？, （, ） y ，, que la hoja de estilo LaTeX muestra como
    los originales.
    @param tipo Tipo en Dart.
    @return Tipo adaptado.
    """
    tipo = tipo.replace('?', '？')
    if tipo.startswith('('):
        tipo = tipo.replace('(', '（').replace(')', '）').replace(',', '，')
    return tipo


def comillas_dobles(texto):
    """
    @brief Cambia las cadenas entre comillas simples por comillas dobles, que Doxygen muestra sin problemas.
    @param texto Fragmento de código.
    @return Fragmento con comillas dobles.
    """
    return re.sub(r"'((?:\\.|[^'\\])*)'", lambda m: '"' + m.group(1).replace('"', '\\"') + '"', texto)


def valor_inicial(texto):
    """
    @brief Resume el valor inicial de un campo para mostrarlo en la documentación.
    @param texto Expresión del valor inicial.
    @return La expresión si es corta; si no, una abreviatura como Clase(…), […] o {…}; o '' si no se puede resumir.
    """
    texto = una_linea(texto)
    if len(texto) <= MAX_INICIAL:
        return comillas_dobles(texto)
    m = re.match(r'^((?:const\s+)?[\w.]+(?:<[^()]*>)?)\s*\(', texto)
    if m:
        return m.group(1) + '(…)'
    if re.match(r'^(const\s*)?\[', texto):
        return ('const ' if texto.startswith('const') else '') + '[…]'
    if re.match(r'^(const\s*)?\{', texto):
        return ('const ' if texto.startswith('const') else '') + '{…}'
    return ''


def separar_tipo_nombre(texto):
    """
    @brief Separa "modificadores tipo nombre" de la declaración de un campo.
    @param texto Declaración sin el valor inicial, p. ej. "static const Duration limite".
    @return Tupla (modificadores, tipo, nombre); el tipo puede ser vacío si Dart lo infiere.
    """
    m = re.match(r'^(.*?)(\w+)$', texto.strip())
    if not m:
        return [], '', texto.strip()
    resto, nombre = m.group(1).strip(), m.group(2)
    modificadores = []
    while True:
        palabra = resto.split(' ', 1)[0] if resto else ''
        if palabra in MODIFICADORES:
            modificadores.append(palabra)
            resto = resto[len(palabra):].strip()
        else:
            break
    return modificadores, resto, nombre


def asignacion_nivel0(texto):
    """
    @brief Posición del primer = de asignación fuera de paréntesis, corchetes y llaves.
    @param texto Encabezado en una línea.
    @return Posición del =, o -1 si no hay (no cuentan ==, =>, <=, >= ni !=).
    """
    nivel = 0
    for i, c in enumerate(texto):
        if c in '([{':
            nivel += 1
        elif c in ')]}':
            nivel -= 1
        elif c == '=' and nivel == 0 and texto[i + 1:i + 2] not in ('=', '>') and texto[i - 1:i] not in ('=', '!', '<', '>'):
            return i
    return -1


def buscar_parametros(encabezado):
    """
    @brief Ubica la lista de parámetros de una función en su encabezado.
    @param encabezado Encabezado en una línea, p. ej. "Future<void> buscar(int a) async".
    @return Tupla (antes del nombre, nombre, contenido de los paréntesis) o None si no es una función.
    """
    asignacion = asignacion_nivel0(encabezado)
    if asignacion >= 0:  # Campo con valor inicial: los paréntesis son de una llamada
        encabezado = encabezado[:asignacion]
    nivel, inicio = 0, None
    for i, c in enumerate(encabezado):
        if c in '([{':
            if nivel == 0 and c == '(':
                inicio = i
            nivel += 1
        elif c in ')]}':
            nivel -= 1
            if nivel == 0 and c == ')' and inicio is not None:
                antes = encabezado[:inicio].rstrip()
                m = re.search(r'([\w$]+(?:\.[\w$]+)?)(?:<[^<>]*>)?$', antes)
                resto = encabezado[i + 1:].strip()
                if m and re.match(r'^(async\*?|sync\*)?\s*(:.*)?$', resto):
                    return antes[:m.start()].strip(), m.group(1), encabezado[inicio + 1:i]
                inicio = None
    return None


def convertir_parametros(contenido, campos):
    """
    @brief Convierte la lista de parámetros de Dart a la forma "tipo nombre" de C++.

    Se quitan las llaves y corchetes de los parámetros con nombre u opcionales; `required` se
    conserva. Los parámetros this.campo y super.key toman el tipo del campo de la clase.
    @param contenido Texto entre los paréntesis.
    @param campos Tipos de los campos de la clase: nombre → tipo.
    @return Parámetros separados por comas.
    """
    contenido = una_linea(contenido)
    nivel = 0
    for i, c in enumerate(contenido):
        if c in '([{':
            if nivel == 0 and c in '[{':
                cierre = _cierre_simple(contenido, i)
                contenido = contenido[:i] + ' ' + contenido[i + 1:cierre] + ' ' + contenido[cierre + 1:]
                break
            nivel += 1
        elif c in ')]}':
            nivel -= 1
    resultado = []
    for parametro in dividir(contenido):
        parametro = sin_anotaciones(parametro)
        requerido = parametro.startswith('required ')
        parametro = re.sub(r'^(required|covariant)\s+', '', parametro)
        partes = dividir(parametro, '=')
        declaracion, defecto = partes[0], ' = '.join(partes[1:])
        m = re.match(r'^(.*?)\b(this|super)\.(\w+)$', declaracion)
        if m:
            nombre = m.group(3)
            tipo = m.group(1).strip() or campos.get(nombre) or ('Key?' if (m.group(2), nombre) == ('super', 'key') else 'var')
        else:
            _, tipo, nombre = separar_tipo_nombre(declaracion)
            tipo = tipo or 'var'
        texto = f"{'required ' if requerido else ''}{tipo} {nombre}"
        resultado.append(texto + (f' = {comillas_dobles(defecto)}' if defecto else ''))
    return ', '.join(resultado)


def _cierre_simple(texto, i):
    """
    @brief Encuentra el cierre del grupo que abre en i, contando (), [] y {}.
    @param texto Texto en una línea.
    @param i Posición del carácter de apertura.
    @return Posición del carácter de cierre.
    """
    nivel = 0
    for j in range(i, len(texto)):
        if texto[j] in '([{':
            nivel += 1
        elif texto[j] in ')]}':
            nivel -= 1
            if nivel == 0:
                return j
    return len(texto) - 1


class Traductor:
    """
    @brief Escribe la versión C++ de un archivo Dart, línea por línea.
    """

    def __init__(self, ruta):
        """
        @brief Lee el archivo y prepara la salida.
        @param ruta Ruta del archivo .dart.
        """
        texto = Path(ruta).read_text(encoding='utf-8').replace('\r\n', '\n')
        ## Archivo analizado.
        self.f = Fuente(texto)
        ## Texto de salida por línea.
        self.salida = [[] for _ in self.f.inicios]
        ## Espacio de nombres del archivo, p. ej. ecoguard_app::pantallas::sos_activo.
        self.espacio = espacio_de_nombres(ruta)

    def emitir(self, linea, texto):
        """
        @brief Agrega texto a una línea de la salida.
        @param linea Número de línea (desde 0).
        @param texto Texto a agregar.
        """
        self.salida[linea].append(texto)

    def emitir_docs(self, desde, hasta):
        """
        @brief Copia a la salida los comentarios /// que hay entre dos posiciones.

        Si el comentario no trae @brief, se le agrega a su primera línea: así Doxygen muestra el primer
        párrafo también en los resúmenes (sin @brief, solo lo hace con los comentarios de una línea).
        @param desde Posición inicial.
        @param hasta Posición final.
        """
        lineas = [n for n in range(self.f.linea(desde), self.f.linea(hasta) + 1)
                  if n in self.f.docs and self.f.inicios[n] < hasta]
        con_brief = any('@brief' in self.f.docs[n] for n in lineas)
        for i, linea in enumerate(lineas):
            texto = self.f.docs[linea]
            if i == 0 and not con_brief:
                texto = re.sub(r'^///\s*', '/// @brief ', texto)
            self.emitir(linea, texto)

    def traducir(self):
        """
        @brief Traduce el archivo completo.
        @return Texto C++ para Doxygen.
        """
        texto = self.f.sin_comentarios
        abierto, anterior = False, 0
        for d in declaraciones(self.f, 0, len(texto)):
            encabezado = sin_anotaciones(una_linea(texto[d.inicio:d.fin_encabezado]))
            if re.match(r'^(library|import|export|part)\b', encabezado):
                if encabezado.startswith('library') and not abierto:
                    self.emitir_docs(anterior, d.inicio)
                    self.emitir(self.f.linea(d.inicio), f'namespace {self.espacio} {{')
                    abierto = True
                anterior = d.fin
                continue
            if not abierto:
                self.emitir(0, f'namespace {self.espacio} {{')
                abierto = True
            self.declaracion(d, encabezado, anterior, None)
            anterior = d.fin
        self.emitir(len(self.salida) - 1, '}')
        return '\n'.join(' '.join(partes) for partes in self.salida) + '\n'

    def declaracion(self, d, encabezado, anterior, clase):
        """
        @brief Traduce una declaración del nivel superior o de una clase.
        @param d Declaracion.
        @param encabezado Encabezado en una línea, sin anotaciones.
        @param anterior Final de la declaración anterior (para ubicar sus comentarios ///).
        @param clase Diccionario con los datos de la clase que la contiene, o None en el nivel superior.
        """
        linea = self.f.linea(d.inicio)
        m = re.match(r'^((?:abstract|base|interface|final|sealed|mixin)\s+)*(class|mixin|enum|extension)\s+(\w+)', encabezado)
        if m and d.tipo_fin == 'llave':
            self.emitir_docs(anterior, d.inicio)
            if m.group(2) == 'enum':
                self.enumeracion(m.group(3), d)
            else:
                self.clase(m.group(3), 'abstract' in (m.group(1) or ''), encabezado[m.end():], d, m.group(2))
            return
        if encabezado.startswith('typedef'):
            m = re.match(r'^typedef\s+(\w+)(?:<[^=]*>)?\s*=\s*(.+)$', encabezado)
            if m:
                self.emitir_docs(anterior, d.inicio)
                self.emitir(linea, f'using {m.group(1)} = {m.group(2)};')
            return
        if re.search(r'\boperator\b|\bset\s+\w+\s*\(', encabezado):
            return

        privado = lambda nombre: nombre.lstrip('$').startswith('_')
        getter = re.match(r'^(.*?)\bget\s+(\w+)$', encabezado)
        funcion = None if getter else buscar_parametros(encabezado)
        if getter:
            modificadores, tipo, _ = separar_tipo_nombre(getter.group(1) + ' x')
            nombre = getter.group(2)
            texto = f"{'static ' if 'static' in modificadores else ''}{tipo_variable(tipo) or 'var'} {nombre};"
            self.miembro(d, anterior, clase, privado(nombre), texto)
        elif funcion:
            antes, nombre, parametros = funcion
            palabras = antes.split()
            modificadores = [p for p in palabras if p in ('static', 'factory', 'const', 'external')]
            retorno = ' '.join(p for p in palabras if p not in modificadores)
            parametros = convertir_parametros(parametros, clase['campos'] if clase else {})
            nombre_clase = clase['nombre'] if clase else None
            if clase and (nombre == nombre_clase or nombre.startswith(nombre_clase + '.')) and not retorno:
                if '.' in nombre:  # Constructor con nombre o factory: se muestra como método estático
                    nombre = nombre.split('.', 1)[1]
                    texto = f'static auto {nombre}({parametros}) -> {nombre_clase};'
                else:
                    texto = f'{nombre}({parametros});'
                    nombre = 'constructor'  # Público aunque la clase sea privada (_Clase)
            else:
                abstracto = clase is not None and clase['abstracta'] and d.tipo_fin == 'punto_y_coma'
                estatico = 'static' in modificadores or (clase is None and privado(nombre))
                virtual = clase is not None and clase['abstracta'] and not estatico
                prefijo = f"{'static ' if estatico else ''}{'virtual ' if virtual else ''}"
                retorno = retorno or 'dynamic'
                if tipo_simple(retorno):
                    texto = f"{prefijo}{retorno} {nombre}({parametros}){' = 0' if abstracto else ''};"
                else:  # Doxygen descarta el ? de un tipo escrito antes del nombre: va al final
                    texto = f"{prefijo}auto {nombre}({parametros}) -> {retorno}{' = 0' if abstracto else ''};"
            self.miembro(d, anterior, clase, privado(nombre), texto)
        else:
            self.variables(d, encabezado, anterior, clase)

    def variables(self, d, encabezado, anterior, clase):
        """
        @brief Traduce la declaración de uno o varios campos o variables.
        @param d Declaracion.
        @param encabezado Encabezado (todo antes del punto y coma).
        @param anterior Final de la declaración anterior.
        @param clase Datos de la clase que la contiene, o None.
        """
        texto = una_linea(self.f.sin_comentarios[d.inicio:d.fin - 1])
        texto = sin_anotaciones(texto)
        declarantes = dividir(texto)
        modificadores, tipo, _ = separar_tipo_nombre(dividir(declarantes[0], '=')[0])
        for i, declarante in enumerate(declarantes):
            partes = dividir(declarante, '=')
            _, _, nombre = separar_tipo_nombre(partes[0])
            inicial = valor_inicial(' = '.join(partes[1:])) if len(partes) > 1 else ''
            estatico = 'static' in modificadores or (clase is None and nombre.startswith('_'))
            prefijo = ' '.join(m for m in modificadores if m in ('const', 'final', 'late'))
            tipo_mostrado = ' '.join(p for p in (prefijo, tipo_variable(tipo)) if p) or 'var'
            salida = f"{'static ' if estatico else ''}{tipo_mostrado} {nombre}{' = ' + inicial if inicial else ''};"
            self.miembro(d, anterior if i == 0 else d.inicio, clase, nombre.startswith('_'), salida)

    def miembro(self, d, anterior, clase, privado, texto):
        """
        @brief Emite un miembro con sus comentarios y, dentro de una clase, su sección de acceso.
        @param d Declaracion.
        @param anterior Final de la declaración anterior.
        @param clase Datos de la clase que la contiene, o None.
        @param privado Verdadero si el nombre empieza con _.
        @param texto Declaración en C++.
        """
        self.emitir_docs(anterior, d.inicio)
        if clase is not None:
            acceso = 'private' if privado else 'public'
            if clase['acceso'] != acceso:
                texto = f'{acceso}: {texto}'
                clase['acceso'] = acceso
        self.emitir(self.f.linea(d.inicio), texto)

    def clase(self, nombre, abstracta, resto, d, tipo):
        """
        @brief Traduce una clase, extensión o mixin con sus miembros.
        @param nombre Nombre de la clase.
        @param abstracta Verdadero si es abstract class.
        @param resto Encabezado después del nombre: extends, with, implements, on.
        @param d Declaracion de la clase.
        @param tipo 'class', 'mixin' o 'extension'. El "on Tipo" de una extensión no es herencia.
        """
        resto = re.sub(r'^<.*?>\s*', '', resto.strip())
        bases = []
        for palabra, lista in re.findall(r'\b(extends|with|implements|on)\s+(.*?)(?=\b(?:extends|with|implements|on)\b|$)', resto):
            if not (palabra == 'on' and tipo == 'extension'):
                bases += dividir(lista)
        herencia = (' : ' + ', '.join(f'public {b}' for b in bases)) if bases else ''
        self.emitir(self.f.linea(d.inicio), f'class {nombre}{herencia} {{ public:')
        apertura, cierre = d.cuerpo
        miembros = declaraciones(self.f, apertura + 1, cierre)
        datos = {'nombre': nombre, 'abstracta': abstracta, 'acceso': 'public', 'campos': {}}
        for m in miembros:  # Primero los tipos de los campos, para los parámetros this.campo
            encabezado = sin_anotaciones(una_linea(self.f.sin_comentarios[m.inicio:m.fin_encabezado]))
            if m.tipo_fin == 'punto_y_coma' and not buscar_parametros(encabezado) and ' get ' not in f' {encabezado} ':
                _, tipo, campo = separar_tipo_nombre(dividir(dividir(encabezado)[0], '=')[0])
                datos['campos'][campo] = tipo
        anterior = apertura + 1
        for m in miembros:
            encabezado = sin_anotaciones(una_linea(self.f.sin_comentarios[m.inicio:m.fin_encabezado]))
            self.declaracion(m, encabezado, anterior, datos)
            anterior = m.fin
        self.emitir(self.f.linea(cierre), '};')

    def enumeracion(self, nombre, d):
        """
        @brief Traduce un enum. De los enums con miembros (enhanced enums) solo se toman los valores.
        @param nombre Nombre del enum.
        @param d Declaracion del enum.
        """
        self.emitir(self.f.linea(d.inicio), f'enum {nombre} {{')
        apertura, cierre = d.cuerpo
        e, i, nivel, inicio = self.f.estructura, apertura + 1, 0, apertura + 1
        anterior = apertura + 1
        while i <= cierre:
            c = e[i]
            if c in '([{':
                nivel += 1
            elif c in ')]}' and i < cierre:
                nivel -= 1
            if nivel == 0 and (c in ',;' or i == cierre):
                valor = una_linea(self.f.sin_comentarios[inicio:i])
                m = re.match(r'^(\w+)', valor)
                if m:
                    posicion = inicio + len(self.f.sin_comentarios[inicio:i]) - len(self.f.sin_comentarios[inicio:i].lstrip())
                    self.emitir_docs(anterior, posicion)
                    self.emitir(self.f.linea(posicion), m.group(1) + ',')
                    anterior = i
                inicio = i + 1
                if c == ';':
                    break
            i += 1
        self.emitir(self.f.linea(cierre), '};')


def espacio_de_nombres(ruta):
    """
    @brief Espacio de nombres de un archivo según su ruta dentro de lib/.
    @param ruta Ruta del archivo, p. ej. .../ecoguard_app/lib/pantallas/sos_activo.dart.
    @return Espacio de nombres, p. ej. ecoguard_app::pantallas::sos_activo.
    """
    partes = Path(ruta).resolve().with_suffix('').parts
    partes = partes[len(partes) - partes[::-1].index('lib'):] if 'lib' in partes else partes[-1:]
    return '::'.join([PAQUETE] + [re.sub(r'\W', '_', p) for p in partes])


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', newline='\n')
    sys.stdout.write(Traductor(sys.argv[1]).traducir())
