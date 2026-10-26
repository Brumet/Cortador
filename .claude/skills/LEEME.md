# Skills de terceros

Las carpetas `replica-*` no son de este proyecto. Son las skills de
[replica-skill](https://github.com/Jakeschincariol/replica-skill) de Jake
Schincariol, con licencia MIT (copia en `LICENSE-replica-skill`), traidas
aqui en el commit `77c9436`.

Estan dentro del repositorio a proposito. Las sesiones en la nube arrancan en
un contenedor limpio y clonan el repositorio entero, asi que lo que vive en
`~/.claude/skills` se pierde entre sesion y sesion y lo que vive aqui no.

Para actualizarlas:

    git clone https://github.com/Jakeschincariol/replica-skill.git
    cp -r replica-skill/replica-* .claude/skills/

Son para clonar una aplicacion desde cero. No hacen falta para trabajar en
Cortador; estan por si se quiere arrancar algo nuevo.
