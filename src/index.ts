import './styles.css';
import './app-root';
// multi-select es un custom element que usan los formularios via `renderer`:
// hay que importarlo aunque ningun archivo lo referencie por nombre.
import './crud/multi-select';
import './modules/consola/consola.page';
import './modules/consola/escucha-viva';
import './modules/consola/contexto-vivo';
import './modules/russ/russ.page';
import './modules/gmail/gmail.page';
// Scripts y tools quedan fuera del bundle a pedido: son las vistas que
// ejecutan comandos en el PC, y mientras Russ aprende a usar herramientas
// preferimos que esa puerta no este. Los archivos siguen ahi; para volver a
// prenderlas hay que descomentar esto y sus rutas en app-root.ts.
// import './modules/scripts/scripts.page';
// import './modules/scripts/scripts.table';
// import './modules/scripts/scripts.form';
// import './modules/tools/tools.page';
// import './modules/tools/tools.table';
// import './modules/tools/tools.form';
import './modules/vision/vision.page';
import './modules/robot/robot.page';
import './modules/caras/caras.page';
import './modules/conocimiento/conocimiento.page';
import './modules/conocimiento/conocimiento.table';
import './modules/conocimiento/conocimiento.form';
import './modules/grafo/grafo-vivo';
import './modules/grafo/grafo.page';
import './modules/sistema/sistema.page';
import './modules/voz/voz.page';
