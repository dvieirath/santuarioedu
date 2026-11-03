# Continuação direta pelo Codex

Foram escritas e salvas 15 justificativas, sem usar Groq ou Gemini. O formato foi preservado: cinco blocos para certo/errado e seis para múltipla escolha. A gravação conferiu enunciado, tipo, alternativas e ausência de justificativa para evitar sobrescrever alterações simultâneas.

Após este lote, permanecem 10.461 questões sem justificativa. Nenhum gerador externo ou processo de geração contínua foi iniciado nesta etapa. A revisão deste lote não representa revisão pedagógica de todo o banco.

## Questões que não receberam justificativa por problemas encontrados

| ID | Problema a revisar |
| --- | --- |
| 9413 | Comparar todos os pares entre sublistas de tamanho proporcional a n pode custar Θ(n²). O enunciado não sustenta a conclusão O(n log n); uma instância fixa de 12 elementos tampouco define, sozinha, uma complexidade assintótica. |
| 9417 | O texto informa conectividade mínima em 45% das áreas rurais; a afirmação converte isso em cobertura total e está marcada como certa. |
| 9458 | Busca em profundidade genérica não garante ordem crescente. Uma árvore de busca exige percurso em ordem para essa garantia; balanceamento não substitui essa condição. |
| 9459 | A soma de 1 a 12 é 78, ausente das alternativas. Além disso, quatro equipes com somas iguais exigiriam soma 19,5 por equipe, impossível para cartões inteiros. |
| 9461 | A execução descrita resulta em 7 + 3 = 10, alternativa A. O gabarito cadastrado marca 14, alternativa B. |
| 9462 | Pelos dados do próprio texto, 68% × 75% = 51%. Não há alternativa compatível com o resultado. |
| 9658 | Trata-se de uma pergunta aberta sobre uma soma, mas o cadastro oferece somente Certo/Errado, sem proposição a julgar. |
| 9663 | A recorrência fornece 3, 7, 23, 67, 203. O quinto termo não aparece nas alternativas e o gabarito aponta 169. |
| 9664 | O enunciado exige três letras e dois dígitos, mas a resposta marcada tem duas letras e um dígito. Também falta explicitar o mapeamento dos níveis de impacto. |
| 2083 | As classes permitem médias entre 1,48 e 1,57 metro; não garantem média inferior a 1,5. A estimativa por pontos médios é 1,525. |
| 2089 | Há ambiguidade entre um aluno fixado antes dos dois sorteios (1/900) e repetir o aluno sorteado primeiro (1/30). O texto precisa esclarecer o evento. |
| 2546 | Para a amostra completa com três observações independentes de Poisson, X1 + X2 não é suficiente: a distribuição de X3, mesmo condicionada à soma, continua dependendo de θ. O gabarito marca Certo. |

Essas questões foram mantidas sem justificativa; seus gabaritos não foram alterados neste lote.

## Fontes consultadas

- [RFC 7518 — HMAC com SHA-2](https://www.rfc-editor.org/rfc/rfc7518.html#section-3.2).
- [MIT — Fibonacci e memoização](https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-fall-2011/resources/mit6_006f11_lec19_orig/).
- [MIT — Programação linear](https://web.mit.edu/lpsolve/doc/LPBasics.htm).
- [MIT — Estatísticas suficientes](https://ocw.mit.edu/courses/14-381-statistical-method-in-economics-fall-2018/download/).
- [NIST — Intervalos de confiança](https://www.itl.nist.gov/div898/handbook/prc/section1/prc14.htm).
- [NIST — Teste qui-quadrado de independência](https://itl.nist.gov/div898/software/dataplot/refman1/auxillar/chistest.htm).
