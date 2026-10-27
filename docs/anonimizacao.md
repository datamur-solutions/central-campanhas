# Como esta versão foi anonimizada

Esta é uma **cópia de portfólio**. O sistema em produção fica num repositório privado e não foi alterado.
A cópia foi feita por um script de limpeza e revisada manualmente.

## O que foi trocado

| Na produção | Nesta versão |
|---|---|
| Marca do grupo educacional | **EduNova** (fictícia), com logo e ícones novos |
| Fornecedores de call center (EPS) | **Voxa**, **Lumen** e **Prisma** (fictícios) |
| E-mails corporativos e de fornecedores | `@edunova.com.br` e `@*.example.com` |
| Endereços do Databricks, do Render e de painéis | Valores de exemplo lidos de variáveis de ambiente (`.env.example`) |
| Catálogos, schemas e tabelas internos | `lakehouse.comercial.*` |
| Nome de usuário e máquina da VM | Usuário de serviço genérico |

## O que foi retirado

- Conectores dos painéis operacionais de parceiros (sistemas de terceiros). A interface foi mantida em `app/robo_vm/paineis_eps.py`, e a conferência com o painel fica registrada como indisponível.
- Prévias de campanhas reais, scripts de migração e de teste, anotações de versão.
- Todo o histórico de commits: este repositório começou do zero.

## O que nunca esteve no código

Senhas, tokens e chaves sempre vieram de variáveis de ambiente ou do cofre do Windows (keyring). Nenhum dado de aluno, lead ou resultado faz parte do repositório: a demonstração usa dados inventados, gerados no próprio navegador (`demo/static/demo-dados.js`).

## Verificação contínua

O workflow `.github/workflows/segredos.yml` roda o [gitleaks](https://github.com/gitleaks/gitleaks) em todo push.
