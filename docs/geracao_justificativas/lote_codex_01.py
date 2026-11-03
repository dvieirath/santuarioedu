"""Conteúdo escrito e revisado no Codex, sem chamadas a provedores externos."""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
items = []

def ce(pk, status, why, trap, concept, reference, memory):
    sections = [(f'🔍 Por que a resposta é {status}', why), ('⚠️ O erro típico', trap),
                ('🧠 Conceito-chave', concept), ('📚 Onde aprofundar', reference),
                ('💡 Padrão a memorizar', memory)]
    items.append({'id': pk, 'justificativa': '\n\n'.join(f'## {h}\n{t}' for h, t in sections)})

ce(9414, 'ERRADO',
   'HS256 usa HMAC com SHA-256 e uma chave secreta compartilhada; não basta calcular um hash simples da mensagem. Além disso, confirmar a assinatura não equivale a validar integralmente o token: a aplicação deve conferir as declarações exigidas, como validade temporal, emissor e destinatário, quando aplicáveis.',
   'Confundir hash com HMAC e autenticidade com validade completa. A verificação criptográfica pode usar o cabeçalho e o payload ainda codificados; o erro não é afirmar que essa etapa dispensa a leitura do JSON, mas reduzir toda a validação a um hash sem chave.',
   'No formato compacto JWS, a entrada autenticada é o cabeçalho codificado, um ponto e o payload codificado. HMAC depende da chave secreta. A interpretação das declarações do payload constitui uma etapa adicional da validação de um JWT.',
   '[RFC 7518, seção 3.2 — HMAC com SHA-2](https://www.rfc-editor.org/rfc/rfc7518.html#section-3.2). Para o processamento das declarações, consulte a RFC 7519.',
   'HS256 = HMAC + SHA-256 + chave. Assinatura válida, sozinha, não garante token adequado à aplicação.')

ce(9415, 'CERTO',
   'Com memoização, cada valor de Fibonacci de 0 até n é calculado no máximo uma vez e depois recuperado do vetor. Há O(n) subproblemas, cada um com trabalho constante, no modelo usual que trata as operações aritméticas como unitárias. Assim, o tempo é O(n); n = 30 é apenas uma instância desse comportamento.',
   'Contar novamente toda a árvore recursiva, como se os resultados não fossem armazenados. A memoização elimina o recálculo dos mesmos subproblemas, embora a implementação ainda use recursão.',
   'Programação dinâmica aproveita subproblemas sobrepostos. A versão recursiva memoizada de Fibonacci usa O(n) posições no vetor e pode usar O(n) posições na pilha. Para inteiros de tamanho arbitrário, o custo em bits das somas requer análise separada.',
   '[MIT — Introduction to Algorithms, aula 19: Memoization e Fibonacci](https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-fall-2011/resources/mit6_006f11_lec19_orig/).',
   'Conte estados distintos, não chamadas repetidas: n estados × trabalho constante = O(n).')

ce(9454, 'CERTO',
   'A razão entre termos consecutivos é 3: 9/3 = 27/9 = 81/27 = 3. A regra declarada no enunciado manda multiplicar cada termo por esse valor. Portanto, 243 × 3 = 729.',
   'Tratar a sequência como uma progressão aritmética. As diferenças são 6, 18 e 54, portanto não são constantes; o que permanece constante é o quociente.',
   'Em uma progressão geométrica, cada termo resulta da multiplicação do anterior pela razão q. Aqui, a sequência é formada por potências consecutivas de 3.',
   'Estude progressões geométricas: razão, recorrência e termo geral.',
   'PG: divida termos vizinhos para encontrar a razão e multiplique para avançar.')

ce(9457, 'ERRADO',
   'Programação linear admite restrições lineares de igualdade e de desigualdade, com diferentes sentidos. Uma restrição como x + y = 10 é perfeitamente compatível com um modelo linear. A não negatividade de variáveis é uma condição de domínio frequente, não uma exigência de que todas as restrições originais tenham uma única forma.',
   'Confundir a forma padronizada exigida por uma apresentação de um algoritmo com a definição geral do problema. Transformações algébricas podem converter restrições em formas equivalentes sem eliminar a diversidade dos modelos originais.',
   'Um programa linear otimiza uma função linear sujeita a restrições lineares. Variáveis de folga transformam certas desigualdades em igualdades; uma variável livre pode ser representada como diferença de duas variáveis não negativas.',
   '[MIT — Linear programming basics](https://web.mit.edu/lpsolve/doc/LPBasics.htm).',
   'Linearidade diz respeito às expressões; não obriga todas as restrições a serem desigualdades do mesmo tipo.')

items.append({'id': 9460, 'justificativa': '''## 🔍 Por que a resposta é essa
A alternativa A está correta: cada termo é o dobro do anterior. Temos 3 × 2 = 6, 6 × 2 = 12, 12 × 2 = 24 e 24 × 2 = 48. Aplicando a mesma regra, o próximo termo é 48 × 2 = 96.

## ⚠️ Armadilhas
- **B)** Somar 24 ao último termo repete um incremento anterior e abandona a duplicação.
- **C)** O valor não corresponde ao produto do último termo pela razão 2.
- **D)** Excede o resultado da duplicação de 48 e rompe a razão constante.
- **E)** Também não mantém o quociente 2 entre termos consecutivos.

## 🧠 Conceito-chave
Esta é uma progressão geométrica de primeiro termo 3 e razão 2. Seu termo geral é a_n = 3 × 2^(n−1). O sexto termo é 3 × 2^5 = 96.

## 🎯 O que esta questão testa
Reconhecimento de um padrão multiplicativo e sua aplicação ao termo seguinte.

## 📚 Onde aprofundar
Estude progressões geométricas, especialmente razão e termo geral.

## 💡 Padrão a memorizar
Quando o quociente entre termos vizinhos é constante, avance multiplicando pela razão.'''} )

ce(9660, 'CERTO',
   'Os dois valores de entrada são 9. Logo, o maior valor do conjunto de entradas é 9, mesmo que ele apareça duas vezes. Um algoritmo que calcula o máximo deve devolver esse valor no caso de empate.',
   'Supor que é necessário existir um valor estritamente superior ao outro para que o máximo esteja definido. A igualdade não impede a existência do máximo.',
   'A função máximo devolve um valor maior ou igual a cada entrada. Para qualquer número a, vale max(a, a) = a.',
   'Estude comparação de valores, operadores relacionais e testes de casos de empate em algoritmos.',
   'Empate entre entradas iguais: o máximo é o próprio valor repetido.')

ce(2547, 'CERTO',
   'A soma dos seis valores é 39 e a média amostral é 39/6 = 6,5. Para a distribuição geométrica na forma dada, com suporte iniciado em zero, a estimativa de máxima verossimilhança de β é 1 + média amostral. Portanto, β estimado = 1 + 6,5 = 7,5.',
   'Usar a média diretamente como estimativa de β ou aplicar a parametrização da geométrica que começa em 1. Aqui, X conta ocorrências anteriores ao primeiro sucesso e E(X) = β − 1.',
   'Com S = soma dos valores e tamanho n, a log-verossimilhança é ℓ(β) = S ln(β − 1) − (n + S) ln β. Sua derivada se anula quando S/(β − 1) = (n + S)/β, isto é, β = 1 + S/n. Para S > 0, a verossimilhança cresce antes desse ponto e decresce depois.',
   'Estude distribuição geométrica com suporte {0, 1, 2, ...}, parametrização e método da máxima verossimilhança.',
   'Nesta parametrização: β estimado = média + 1. Confira sempre onde começa o suporte.')

ce(2548, 'CERTO',
   'A afirmação apresenta a definição de suficiência: depois de conhecido o valor da estatística, a distribuição condicional da amostra não depende do parâmetro. Assim, dentro do modelo considerado, a amostra não fornece informação adicional sobre o parâmetro além daquela retida pela estatística.',
   'Confundir suficiência com ausência de viés ou com pequena variância. Essas são propriedades diferentes; uma estatística suficiente não precisa ser, por si só, um estimador não viesado.',
   'Uma estatística T(X) é função da amostra. Ela é suficiente para θ quando a lei condicional de X dado T(X) é independente de θ. Sob as condições usuais, o teorema de fatoração fornece um critério equivalente para verificar a suficiência.',
   '[MIT — Statistical Method in Economics, material sobre estatísticas suficientes](https://ocw.mit.edu/courses/14-381-statistical-method-in-economics-fall-2018/download/).',
   'Suficiência: conhecido T, a distribuição condicional da amostra não depende de θ.')

ce(2549, 'ERRADO',
   'Com desvio padrão populacional conhecido, a amplitude do intervalo bilateral é 2zσ/√n. Mantendo z e σ constantes, aumentar n reduz a amplitude. Neste caso, ela passa de 2 × 1,88 × 3,50/√25 = 2,632 para aproximadamente 2,487 pontos quando n = 28.',
   'Pensar que uma amostra maior aumenta a incerteza. O maior tamanho amostral reduz o erro padrão da média e estreita o intervalo, mantidas as condições indicadas.',
   'O erro padrão da média é σ/√n. A margem de erro é z vezes esse erro padrão, e a amplitude total é duas vezes a margem.',
   '[NIST — What are confidence intervals?](https://www.itl.nist.gov/div898/handbook/prc/section1/prc14.htm).',
   'Mais observações, menor erro padrão: a largura varia com 1/√n.')

ce(2553, 'CERTO',
   'O valor observado, 9,10, é menor que o valor crítico informado, 10,7. Portanto, ele não pertence à região de rejeição à direita e não se rejeita a hipótese de independência ao nível de 3%. Os números já fornecidos permitem essa decisão sem reconstruir a tabela.',
   'Inverter a comparação ou interpretar a não rejeição como prova de independência. O resultado significa apenas que o teste não encontrou evidência suficiente contra H0 nesse nível de significância.',
   'No teste qui-quadrado de independência, valores elevados da estatística indicam maior discrepância entre frequências observadas e esperadas. Para uma tabela 3 × 3, há (3 − 1)(3 − 1) = 4 graus de liberdade.',
   '[NIST — Chi-square independence test](https://itl.nist.gov/div898/software/dataplot/refman1/auxillar/chistest.htm).',
   'Qui-quadrado de independência: rejeite H0 quando a estatística ultrapassar o valor crítico.')

ce(2556, 'CERTO',
   'No modelo E(Y | x) = a + bx, substituir x por x + 1 altera a média prevista de a + bx para a + bx + b. A diferença é b. Logo, esse coeficiente mede a variação média do tempo associada ao aumento de uma unidade de renda.',
   'Confundir b com o tempo inicial a ou com a mudança de cada indivíduo. A regressão descreve a média condicional; não garante a mesma alteração para todo cliente nem demonstra causalidade por si só.',
   'Em regressão linear simples, a é o intercepto e b é a inclinação. Como Y está em anos e X em salários mínimos, b tem unidade de anos por salário mínimo.',
   'Estude regressão linear simples: média condicional, intercepto e interpretação da inclinação.',
   'Em a + bx, aumentar x em uma unidade muda a média prevista em b.')

ce(2712, 'ERRADO',
   'As forças de um binário têm módulos iguais e sentidos opostos, com linhas de ação paralelas e distintas. O enunciado erra ao dizer que têm o mesmo sentido. Em um binário, a força resultante é nula, mas o momento resultante pode ser não nulo.',
   'Confundir mesma direção com mesmo sentido. Duas forças paralelas podem ter sentidos opostos; se tiverem o mesmo sentido, seus módulos se somam e não formam um binário.',
   'Para forças de módulo F cujas linhas de ação estão separadas pela distância perpendicular d, o módulo do momento do binário é Fd. Por ter força resultante nula, esse momento não depende do ponto de referência.',
   'Estude estática dos corpos rígidos: sistemas de forças, binários e momento de um conjugado.',
   'Binário: forças iguais e opostas, linhas distintas, resultante zero e momento Fd.')

ce(2713, 'ERRADO',
   'Para forças perpendiculares de módulos F1 e F2, o módulo da resultante é √(F1² + F2²). Essa relação vem do teorema de Pitágoras, aplicado à soma vetorial. A média aritmética não calcula o módulo da resultante.',
   'Tratar forças como números sem direção e fazer uma média. Por exemplo, forças perpendiculares de 3 N e 4 N produzem resultante de 5 N, e não de 3,5 N.',
   'A soma de vetores depende do ângulo entre eles. Em geral, R² = F1² + F2² + 2F1F2 cos θ; quando θ = 90°, o termo com cosseno é zero.',
   'Estude soma vetorial, teorema de Pitágoras e lei dos cossenos aplicada a forças.',
   'Vetores perpendiculares: some os quadrados dos módulos e extraia a raiz.')

ce(2714, 'CERTO',
   'A regra do paralelogramo representa as duas forças a partir da mesma origem. A diagonal que sai dessa origem e chega ao vértice oposto representa a soma vetorial. Medir seu comprimento e aplicar a escala do desenho fornece o módulo da resultante.',
   'Escolher a outra diagonal ou somar apenas os comprimentos dos lados. O sentido da diagonal deve partir da origem comum; a soma dos módulos só coincide com o módulo da resultante em um caso particular de forças de mesmo sentido.',
   'A resultante R = F1 + F2 reúne os efeitos das duas forças concorrentes. A construção gráfica considera simultaneamente suas direções, sentidos e intensidades.',
   'Estude adição de vetores pelos métodos do paralelogramo e do polígono.',
   'A diagonal que nasce na origem comum representa a soma dos vetores.')

ce(2740, 'ERRADO',
   'A relação correta é v_B − v_A = ω × r_B/A, em que ω é a velocidade angular do corpo rígido. O enunciado usa indevidamente a velocidade linear de A no produto vetorial. É a rotação, representada por ω, que determina a velocidade relativa entre os pontos.',
   'Trocar velocidade angular por velocidade linear. A análise dimensional já revela o problema: velocidade linear multiplicada por comprimento não tem unidade de velocidade.',
   'No movimento de um corpo rígido, v_B = v_A + ω × r_B/A. O primeiro termo representa a translação do ponto de referência; o segundo expressa a contribuição da rotação.',
   'Estude cinemática dos corpos rígidos: campo de velocidades e decomposição em translação e rotação.',
   'Velocidade relativa em corpo rígido: velocidade angular × posição relativa.')

(BASE / 'lote_codex_01_respostas.json').write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'{len(items)} justificativas autorais preparadas.')
