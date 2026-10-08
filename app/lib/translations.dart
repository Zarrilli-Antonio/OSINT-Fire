import 'tr_core.dart';
import 'tr_dialogs.dart';
import 'tr_graph.dart';
import 'tr_main.dart';
import 'tr_settings.dart';

/// Interface strings: English source text -> [Italian, Spanish, German]. English needs no entry.
final Map<String, List<String>> kTranslations = {...trCore, ...trMain, ...trSettings, ...trGraph, ...trDialogs};
